from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

import psycopg
import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.media import MediaRecord
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_project_management import (
    PostgresProjectManagementService,
)
from natureai_next.server.postgres_science import PostgresScienceRepository


def _dsn() -> str:
    value = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not value:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    return value


def _connect_factory():
    dsn = _dsn()
    return lambda: psycopg.connect(dsn, connect_timeout=10)


def _run_concurrently(factory) -> None:
    barrier = threading.Barrier(8)

    def initialize() -> None:
        barrier.wait(timeout=10)
        factory()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(initialize) for _ in range(8)]
        for future in futures:
            future.result(timeout=30)


def _race(*operations):
    barrier = threading.Barrier(len(operations))

    def invoke(operation):
        barrier.wait(timeout=10)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(invoke, operation) for operation in operations]
        return tuple(future.result(timeout=30) for future in futures)


@dataclass(frozen=True)
class _Identity:
    identity_id: str
    organization_id: str


@dataclass(frozen=True)
class _Decision:
    allowed: bool


@dataclass(frozen=True)
class _EvidenceRecord:
    media_id: str
    organization_id: str
    project_id: str


class _EvidenceMedia:
    def __init__(self, organization_id: str, project_id: str) -> None:
        self.items = {
            media_id: _EvidenceRecord(media_id, organization_id, project_id)
            for media_id in ("asset-primary", "asset-2", "asset-3")
        }
        self.register_calls = 0

    def record(self, media_id: str):
        return self.items.get(media_id)

    def register(self, *_args, **_kwargs):
        self.register_calls += 1
        raise AssertionError("observation links must not clone governed evidence")


class _Decisions:
    def __init__(self) -> None:
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return _Decision(request.subject_id != "denied-user")


class _ObservationBase:
    def __init__(
        self,
        science: PostgresScienceRepository,
        organization_id: str,
        project_id: str,
    ) -> None:
        self._science = science
        self._media = _EvidenceMedia(organization_id, project_id)
        self._decisions = _Decisions()
        self._governance = None
        self._organization_id = organization_id

    def _identity(self, headers):
        subject = headers.get("x-test-subject", "allowed-user")
        return "test-token", _Identity(subject, self._organization_id)

    def dispatch(self, _method, _target, _headers, _body):
        return ApiResponse.json(404, {"error": "not_found"})


class _ObservationApi(ObservationParityApiMixin, _ObservationBase):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def _create_observation(api: _ObservationApi, project_id: str) -> str:
    response = api.dispatch(
        "POST",
        "/api/v1/observations",
        {"x-test-subject": "creator-user"},
        json.dumps(
            {
                "project_id": project_id,
                "asset_id": "asset-primary",
                "observation_type": "organism",
            }
        ).encode(),
    )
    assert response.status == 201
    return str(_payload(response)["item"]["id"])


def _observation(science: PostgresScienceRepository, observation_id: str) -> dict:
    return next(
        item
        for item in science.records("server_observations")
        if str(item.get("id", "")) == observation_id
    )


def test_science_schema_bootstrap_is_safe_for_concurrent_api_and_worker_start() -> None:
    dsn = _dsn()
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("DROP TABLE IF EXISTS science_records CASCADE")
        connection.execute("DROP TABLE IF EXISTS science_state CASCADE")

    _run_concurrently(
        lambda: PostgresScienceRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    )

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        state = connection.execute(
            "SELECT revision FROM science_state WHERE singleton=TRUE"
        ).fetchone()
    assert state == (0,)


def test_media_schema_bootstrap_is_safe_for_concurrent_api_and_worker_start() -> None:
    dsn = _dsn()
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        connection.execute("DROP TABLE IF EXISTS governed_media_associations CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_media_instances CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_uploads CASCADE")
        connection.execute("DROP TABLE IF EXISTS governed_media CASCADE")

    _run_concurrently(
        lambda: PostgresMediaMetadataRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    )

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        media = connection.execute("SELECT count(*) FROM governed_media").fetchone()
        instances = connection.execute(
            "SELECT count(*) FROM governed_media_instances"
        ).fetchone()
        uploads = connection.execute("SELECT count(*) FROM governed_uploads").fetchone()
        associations = connection.execute(
            "SELECT count(*) FROM governed_media_associations"
        ).fetchone()
    assert media == (0,)
    assert instances == (0,)
    assert uploads == (0,)
    assert associations == (0,)


@pytest.mark.integration
def test_web054_concurrent_project_edits_preserve_one_revision_winner() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-web054-project-{uuid4()}"
    owner_id = f"user-owner-{uuid4()}"
    project_id = service.create_project(
        "Concurrent project",
        organization_id=organization_id,
        owner_id=owner_id,
        actor_id=owner_id,
    )
    created = next(
        item for item in service.projects(organization_id) if item.project_id == project_id
    )

    def edit(name: str, actor_id: str):
        try:
            revision = service.update_project(
                project_id,
                organization_id=organization_id,
                actor_id=actor_id,
                expected_revision=created.revision,
                name=name,
            )
        except ValueError as exc:
            return "conflict", str(exc)
        return "updated", revision

    results = _race(
        lambda: edit("Alice wins", f"user-alice-{uuid4()}"),
        lambda: edit("Bob wins", f"user-bob-{uuid4()}"),
    )
    assert sorted(result[0] for result in results) == ["conflict", "updated"]
    conflict = next(result for result in results if result[0] == "conflict")
    assert "revision conflict" in conflict[1]

    current = next(
        item for item in service.projects(organization_id) if item.project_id == project_id
    )
    winner = next(result for result in results if result[0] == "updated")
    assert current.revision == winner[1]
    assert current.revision > created.revision
    assert current.name in {"Alice wins", "Bob wins"}


@pytest.mark.integration
def test_web054_concurrent_duplicate_imports_converge_on_one_media_identity() -> None:
    repository = PostgresMediaMetadataRepository(_connect_factory())
    organization_id = f"org-web054-media-{uuid4()}"
    project_id = f"project-{uuid4()}"
    digest = "ab" * 32
    first = MediaRecord(
        str(uuid4()),
        f"objects/{uuid4()}",
        organization_id,
        project_id,
        "image/jpeg",
        4096,
        digest,
    )
    second = MediaRecord(
        str(uuid4()),
        f"objects/{uuid4()}",
        organization_id,
        project_id,
        "image/jpeg",
        4096,
        digest,
    )

    canonicals = _race(
        lambda: repository.insert_media(first),
        lambda: repository.insert_media(second),
    )

    assert len({record.media_id for record in canonicals}) == 1
    canonical_id = canonicals[0].media_id
    stored = tuple(
        record
        for record in repository.records(organization_id)
        if record.sha256 == digest and record.size_bytes == 4096
    )
    assert [record.media_id for record in stored] == [canonical_id]
    instances = repository.instances(canonical_id, organization_id)
    assert len(instances) == 1
    assert instances[0].storage_kind == "managed"


@pytest.mark.integration
def test_web054_concurrent_evidence_links_preserve_revision_identity_and_pbac() -> None:
    science = PostgresScienceRepository(_connect_factory())
    organization_id = f"org-web054-links-{uuid4()}"
    project_id = f"project-{uuid4()}"
    api = _ObservationApi(science, organization_id, project_id)
    observation_id = _create_observation(api, project_id)

    responses = _race(
        lambda: api.dispatch(
            "POST",
            f"/api/v1/observations/{observation_id}/evidence",
            {"if-match": "1", "x-test-subject": "linker-alice"},
            b'{"asset_id":"asset-2"}',
        ),
        lambda: api.dispatch(
            "POST",
            f"/api/v1/observations/{observation_id}/evidence",
            {"if-match": "1", "x-test-subject": "linker-bob"},
            b'{"asset_id":"asset-3"}',
        ),
    )
    assert sorted(response.status for response in responses) == [200, 409]

    current = _observation(science, observation_id)
    assert current["revision"] == 2
    assert current["asset_id"] == "asset-primary"
    assert len(current["supporting_asset_ids"]) == 1
    assert current["supporting_asset_ids"][0] in {"asset-2", "asset-3"}
    assert api._media.register_calls == 0

    denied = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "2", "x-test-subject": "denied-user"},
        b'{"asset_id":"asset-2"}',
    )
    assert denied.status == 403
    assert _observation(science, observation_id) == current
    denied_request = next(
        request
        for request in api._decisions.requests
        if request.subject_id == "denied-user"
    )
    assert denied_request.action == "edit"
    assert denied_request.resource_type == "observation"
    assert denied_request.organization_id == organization_id
    assert denied_request.project_id == project_id


@pytest.mark.integration
def test_web054_concurrent_reviews_preserve_revision_and_pbac() -> None:
    science = PostgresScienceRepository(_connect_factory())
    organization_id = f"org-web054-review-{uuid4()}"
    project_id = f"project-{uuid4()}"
    api = _ObservationApi(science, organization_id, project_id)
    observation_id = _create_observation(api, project_id)

    responses = _race(
        lambda: api.dispatch(
            "PATCH",
            f"/api/v1/observations/{observation_id}",
            {"if-match": "1", "x-test-subject": "reviewer-alice"},
            b'{"confirmation_state":"confirmed"}',
        ),
        lambda: api.dispatch(
            "PATCH",
            f"/api/v1/observations/{observation_id}",
            {"if-match": "1", "x-test-subject": "reviewer-bob"},
            b'{"confirmation_state":"rejected"}',
        ),
    )
    assert sorted(response.status for response in responses) == [200, 409]

    current = _observation(science, observation_id)
    assert current["revision"] == 2
    assert current["confirmation_state"] in {"confirmed", "rejected"}

    denied_state = (
        "rejected" if current["confirmation_state"] == "confirmed" else "confirmed"
    )
    denied = api.dispatch(
        "PATCH",
        f"/api/v1/observations/{observation_id}",
        {"if-match": "2", "x-test-subject": "denied-user"},
        json.dumps({"confirmation_state": denied_state}).encode(),
    )
    assert denied.status == 403
    assert _observation(science, observation_id) == current
