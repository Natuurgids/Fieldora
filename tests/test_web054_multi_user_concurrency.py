from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.knowledge_parity_api import KnowledgeParityApiMixin
from natureai_next.server.media import GovernedMediaStore, MediaRecord
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.postgres_project_management import PostgresProjectManagementService


@dataclass(frozen=True)
class _Identity:
    identity_id: str
    organization_id: str = "org-1"


@dataclass(frozen=True)
class _MediaRecord:
    media_id: str
    organization_id: str = "org-1"
    project_id: str = "project-1"


class _Media:
    def __init__(self) -> None:
        self.items = {
            media_id: _MediaRecord(media_id)
            for media_id in ("asset-primary", "asset-a", "asset-b")
        }
        self.register_calls = 0

    def record(self, media_id: str):
        return self.items.get(media_id)

    def register(self, *_args, **_kwargs):
        self.register_calls += 1
        raise AssertionError("concurrent observation links must not clone evidence")


class _Science:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, tuple[dict, int]]] = {}
        self._lock = threading.Lock()

    def records(self, collection: str):
        with self._lock:
            return tuple(
                dict(item) for item, _revision in self.items.get(collection, {}).values()
            )

    def put(self, collection: str, record: dict, expected_revision: int | None):
        with self._lock:
            bucket = self.items.setdefault(collection, {})
            record_id = str(record["id"])
            current = bucket.get(record_id)
            current_revision = 0 if current is None else current[1]
            if expected_revision is not None and expected_revision != current_revision:
                raise ValueError("revision_conflict")
            revision = current_revision + 1
            bucket[record_id] = (dict(record), revision)
            return revision


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


class _Decisions:
    def __init__(self, denied_subject: str = "") -> None:
        self.denied_subject = denied_subject
        self.subjects: list[str] = []
        self._lock = threading.Lock()

    def decide(self, request):
        with self._lock:
            self.subjects.append(request.subject_id)
        return _Decision(request.subject_id != self.denied_subject)


class _ObservationBase:
    def __init__(
        self,
        identity: _Identity,
        science: _Science,
        media: _Media,
        decisions: _Decisions,
    ) -> None:
        self.identity = identity
        self._science = science
        self._media = media
        self._decisions = decisions
        self._governance = None

    def _identity(self, _headers):
        return "token", self.identity

    def dispatch(self, _method, _target, _headers, _body):
        return ApiResponse.json(404, {"error": "not_found"})


class _ObservationApi(ObservationParityApiMixin, _ObservationBase):
    pass


class _KnowledgeBase:
    def __init__(self, identity: _Identity, science: _Science, decisions: _Decisions) -> None:
        self.identity = identity
        self._science = science
        self._decisions = decisions

    def _identity(self, _headers):
        return "token", self.identity

    def dispatch(self, _method, _target, _headers, _body):
        return ApiResponse.json(404, {"error": "not_found"})


class _KnowledgeApi(KnowledgeParityApiMixin, _KnowledgeBase):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def test_concurrent_users_linking_observation_evidence_preserve_revision_and_pbac() -> None:
    science = _Science()
    media = _Media()
    decisions = _Decisions()
    creator = _ObservationApi(_Identity("user-a"), science, media, decisions)
    created = creator.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        b'{"project_id":"project-1","asset_id":"asset-primary","observation_type":"unknown"}',
    )
    assert created.status == 201
    observation_id = _payload(created)["item"]["id"]

    barrier = threading.Barrier(2)

    def link(subject: str, asset_id: str) -> int:
        api = _ObservationApi(_Identity(subject), science, media, decisions)
        barrier.wait(timeout=10)
        return api.dispatch(
            "POST",
            f"/api/v1/observations/{observation_id}/evidence",
            {"if-match": "1"},
            json.dumps({"asset_id": asset_id}).encode(),
        ).status

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(link, "user-a", "asset-a")
        second = executor.submit(link, "user-b", "asset-b")
        statuses = sorted((first.result(timeout=20), second.result(timeout=20)))

    assert statuses == [200, 409]
    final, revision = science.items["server_observations"][observation_id]
    assert revision == 2
    assert len(final["supporting_asset_ids"]) == 1
    assert set(final["supporting_asset_ids"]) <= {"asset-a", "asset-b"}
    assert media.register_calls == 0
    assert {"user-a", "user-b"}.issubset(set(decisions.subjects))


def test_pbac_denial_during_contention_cannot_mutate_observation() -> None:
    science = _Science()
    media = _Media()
    decisions = _Decisions(denied_subject="user-denied")
    creator = _ObservationApi(_Identity("user-a"), science, media, decisions)
    created = creator.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        b'{"project_id":"project-1","asset_id":"asset-primary","observation_type":"unknown"}',
    )
    observation_id = _payload(created)["item"]["id"]

    denied = _ObservationApi(
        _Identity("user-denied"), science, media, decisions
    ).dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"asset-a"}',
    )
    assert denied.status == 403
    final, revision = science.items["server_observations"][observation_id]
    assert revision == 1
    assert final["supporting_asset_ids"] == []


def test_concurrent_reviewers_cannot_resolve_one_proposal_twice() -> None:
    science = _Science()
    decisions = _Decisions()
    creator = _KnowledgeApi(_Identity("reviewer-a"), science, decisions)
    proposal = {
        "project_id": "project-1",
        "provider_key": "human-field-note",
        "subject": {"subject_type": "observation", "public_id": "obs-1"},
        "candidate": {
            "shape": "taxonomy_candidate",
            "value": {"scientific_name": "Ardea cinerea"},
            "confidence": 0.92,
            "target": {},
            "external_id": "taxon:ardea-cinerea",
        },
        "source_snapshot": {
            "producer_name": "human-field-note",
            "producer_version": "1",
            "source_name": "Field notebook",
            "source_version": "2026.08",
            "checksum": "sha256:abc",
            "attribution": "Fieldora",
            "licence": "internal",
            "created_at_us": 123456,
        },
    }
    created = creator.dispatch(
        "POST", "/api/v1/knowledge", {}, json.dumps(proposal).encode()
    )
    assert created.status == 201
    proposal_id = _payload(created)["item"]["id"]
    barrier = threading.Barrier(2)

    def review(subject: str, action: str) -> int:
        api = _KnowledgeApi(_Identity(subject), science, decisions)
        barrier.wait(timeout=10)
        return api.dispatch(
            "POST",
            f"/api/v1/knowledge/{proposal_id}/review",
            {"if-match": "1"},
            json.dumps({"action": action}).encode(),
        ).status

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(review, "reviewer-a", "accept")
        second = executor.submit(review, "reviewer-b", "reject")
        statuses = sorted((first.result(timeout=20), second.result(timeout=20)))

    assert statuses == [200, 409]
    final, revision = science.items["server_knowledge_proposals"][proposal_id]
    assert revision == 2
    assert final["review_state"] in {"accepted", "rejected"}
    assert len(science.items.get("server_knowledge_review_actions", {})) == 1
    assert {"reviewer-a", "reviewer-b"}.issubset(set(decisions.subjects))


def test_concurrent_uploads_from_two_users_converge_on_one_evidence_identity(
    tmp_path: Path,
) -> None:
    store = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "objects")
    payload = b"same scientific evidence bytes from two users"
    digest = hashlib.sha256(payload).hexdigest()
    uploads = [
        store.begin_upload(
            subject,
            "org-1",
            "project-1",
            f"{subject}.bin",
            "application/octet-stream",
            len(payload),
            digest,
        )
        for subject in ("user-a", "user-b")
    ]
    barrier = threading.Barrier(2)

    def complete(upload) -> MediaRecord:
        barrier.wait(timeout=10)
        result = store.append_upload(upload, 0, payload)
        assert isinstance(result, MediaRecord)
        return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(complete, uploads))

    assert records[0].media_id == records[1].media_id
    assert len(store.records("org-1")) == 1
    assert len(store.instances(records[0].media_id, "org-1")) == 1


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


@pytest.mark.integration
def test_concurrent_project_edits_allow_one_revision_winner() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-web054-{uuid4()}"
    owner = f"user-a-{uuid4()}"
    other = f"user-b-{uuid4()}"
    project_id = service.create_project(
        "Concurrent Project",
        organization_id=organization_id,
        owner_id=owner,
        actor_id=owner,
    )
    created = next(
        item for item in service.projects(organization_id) if item.project_id == project_id
    )
    barrier = threading.Barrier(2)

    def edit(actor: str, name: str) -> tuple[str, int | None]:
        barrier.wait(timeout=10)
        try:
            revision = service.update_project(
                project_id,
                organization_id=organization_id,
                actor_id=actor,
                expected_revision=created.revision,
                name=name,
            )
        except ValueError as exc:
            assert "revision conflict" in str(exc)
            return "conflict", None
        return "ok", revision

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(edit, owner, "Edit from user A")
        second = executor.submit(edit, other, "Edit from user B")
        results = (first.result(timeout=20), second.result(timeout=20))

    assert sorted(result[0] for result in results) == ["conflict", "ok"]
    winner_revision = next(result[1] for result in results if result[0] == "ok")
    current = next(
        item for item in service.projects(organization_id) if item.project_id == project_id
    )
    assert current.revision == winner_revision
    assert current.name in {"Edit from user A", "Edit from user B"}
