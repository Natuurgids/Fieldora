from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from natureai_next.domain.access_control import (
    AccessDecision,
    Identity,
    IdentityKind,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_sync import OfflineSyncStore
from natureai_next.server.offline_sync_api import OfflineSyncApiMixin


class _Decisions:
    def __init__(self, denied_record: str = "") -> None:
        self.denied_record = denied_record
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        allowed = request.logical_record_id != self.denied_record if hasattr(request, "logical_record_id") else request.resource_id != self.denied_record
        return AccessDecision(allowed, "test")


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(OfflineSyncApiMixin, _BaseApi):
    def __init__(self, root: Path, *, denied_record: str = "") -> None:
        self._offline_sync = OfflineSyncStore(root / "offline-sync.sqlite3")
        self._decisions = _Decisions(denied_record)
        self.identity = Identity(
            "researcher-1", IdentityKind.USER, "Researcher", "org-1"
        )

    def _identity(self, headers):
        if headers.get("authorization") != "Bearer good-token":
            from natureai_next.application.authentication import AuthenticationFailed

            raise AuthenticationFailed("invalid token")
        return "good-token", self.identity


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _assertion(logical_id: str, value: str, *, assertion_id: str | None = None) -> dict:
    return {
        "assertion_id": assertion_id or str(uuid4()),
        "logical_record_id": logical_id,
        "record_type": "observation",
        "organization_id": "org-1",
        "project_id": "project-1",
        "author_identity_id": "researcher-1",
        "device_id": "tablet-1",
        "created_at_utc": _now(),
        "payload": {"taxon": value},
        "contract_id": "contract-1",
        "evidence_ids": ["media-1"],
    }


def _bundle(assertions: list[dict], *, source_identity_id: str = "researcher-1") -> dict:
    return {
        "bundle_id": str(uuid4()),
        "organization_id": "org-1",
        "source_device_id": "tablet-1",
        "source_identity_id": source_identity_id,
        "created_at_utc": _now(),
        "assertions": assertions,
        "metadata": {"client": "mobile"},
    }


def _post(api: _Api, path: str, payload: dict):
    return api.dispatch(
        "POST",
        path,
        {"authorization": "Bearer good-token", "x-fieldora-purpose": "research"},
        json.dumps(payload).encode(),
    )


def test_sync_bundle_is_bound_to_authenticated_identity(tmp_path: Path) -> None:
    api = _Api(tmp_path)
    response = _post(
        api,
        "/api/v1/sync/bundles",
        _bundle([_assertion("obs-1", "Species A")], source_identity_id="someone-else"),
    )
    assert response.status == 403
    assert json.loads(response.body)["error"] == "sync_identity_mismatch"


def test_sync_pbac_rejects_only_unauthorized_assertions(tmp_path: Path) -> None:
    api = _Api(tmp_path, denied_record="obs-denied")
    allowed = _assertion("obs-allowed", "Species A")
    denied = _assertion("obs-denied", "Species B")
    response = _post(api, "/api/v1/sync/bundles", _bundle([allowed, denied]))
    payload = json.loads(response.body)

    assert response.status == 202
    assert payload["inserted_assertion_ids"] == [allowed["assertion_id"]]
    assert payload["rejected_assertion_ids"] == [denied["assertion_id"]]
    assert len(api._offline_sync.assertions("org-1", "observation", "obs-allowed")) == 1
    assert api._offline_sync.assertions("org-1", "observation", "obs-denied") == ()


def test_sync_preserves_conflicts_until_explicit_resolution(tmp_path: Path) -> None:
    api = _Api(tmp_path)
    first = _assertion("obs-1", "Panthera onca")
    second = _assertion("obs-1", "Puma concolor")
    assert _post(api, "/api/v1/sync/bundles", _bundle([first])).status == 200
    conflict = _post(api, "/api/v1/sync/bundles", _bundle([second]))
    assert json.loads(conflict.body)["conflict_record_ids"] == ["obs-1"]

    before = api.dispatch(
        "GET",
        "/api/v1/sync/presentation?record_type=observation&logical_record_id=obs-1&project_id=project-1",
        {"authorization": "Bearer good-token"},
        b"",
    )
    before_payload = json.loads(before.body)
    assert before_payload["assertion"] is None
    assert before_payload["requires_resolution"] is True

    resolution = {
        "resolution_id": str(uuid4()),
        "logical_record_id": "obs-1",
        "record_type": "observation",
        "project_id": "project-1",
        "primary_assertion_id": first["assertion_id"],
        "decided_at_utc": _now(),
        "rationale": "reviewed evidence",
        "audience": "organization",
    }
    assert _post(api, "/api/v1/sync/resolutions", resolution).status == 201

    after = api.dispatch(
        "GET",
        "/api/v1/sync/presentation?record_type=observation&logical_record_id=obs-1&project_id=project-1",
        {"authorization": "Bearer good-token"},
        b"",
    )
    after_payload = json.loads(after.body)
    assert after_payload["assertion"]["assertion_id"] == first["assertion_id"]
    assert after_payload["requires_resolution"] is False
    assert len(api._offline_sync.assertions("org-1", "observation", "obs-1")) == 2
