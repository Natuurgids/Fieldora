from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.observation_parity_api import ObservationParityApiMixin


@dataclass
class _Identity:
    identity_id: str = "researcher-1"
    organization_id: str = "org-1"


@dataclass
class _MediaRecord:
    media_id: str
    organization_id: str = "org-1"
    project_id: str = "project-1"


class _Media:
    def __init__(self) -> None:
        self.item = _MediaRecord("asset-1")
        self.record_calls: list[str] = []
        self.register_calls = 0

    def record(self, media_id: str):
        self.record_calls.append(media_id)
        return self.item if media_id == self.item.media_id else None

    def register(self, *_args, **_kwargs):
        self.register_calls += 1
        raise AssertionError("observation creation must never clone/register evidence")


class _Science:
    def __init__(self) -> None:
        self.items: dict[str, tuple[dict, int]] = {}

    def records(self, collection: str):
        assert collection == "server_observations"
        return tuple(dict(item) for item, _revision in self.items.values())

    def put(self, collection: str, record: dict, expected_revision: int | None):
        assert collection == "server_observations"
        record_id = str(record["id"])
        current = self.items.get(record_id)
        current_revision = 0 if current is None else current[1]
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError("revision_conflict")
        revision = current_revision + 1
        self.items[record_id] = (dict(record), revision)
        return revision


class _Decision:
    allowed = True


class _Decisions:
    def decide(self, _request):
        return _Decision()


class _Base:
    def __init__(self) -> None:
        self._media = _Media()
        self._science = _Science()
        self._decisions = _Decisions()
        self._governance = None

    def _identity(self, _headers):
        return "token", _Identity()

    def dispatch(self, _method, _target, _headers, _body):
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(ObservationParityApiMixin, _Base):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def test_create_links_existing_evidence_without_cloning_and_uses_server_id() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        json.dumps(
            {
                "id": "browser-must-not-own-this-id",
                "project_id": "project-1",
                "asset_id": "asset-1",
                "observation_type": "organism",
                "count": 2,
                "life_stage": "adult",
                "notes": "Seen on existing evidence.",
            }
        ).encode(),
    )

    assert response.status == 201
    payload = _payload(response)
    item = payload["item"]
    assert item["id"] != "browser-must-not-own-this-id"
    assert item["asset_id"] == "asset-1"
    assert item["observation_type"] == "organism"
    assert item["count"] == 2
    assert item["confirmation_state"] == "unconfirmed"
    assert item["source"] == "user"
    assert payload["revision"] == 1
    assert api._media.record_calls == ["asset-1"]
    assert api._media.register_calls == 0


def test_create_rejects_missing_or_cross_project_evidence() -> None:
    api = _Api()
    missing = api.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        b'{"project_id":"project-1","asset_id":"missing","observation_type":"unknown"}',
    )
    assert missing.status == 404
    assert _payload(missing)["error"] == "evidence_not_found"

    api._media.item.project_id = "project-2"
    mismatch = api.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        b'{"project_id":"project-1","asset_id":"asset-1","observation_type":"unknown"}',
    )
    assert mismatch.status == 409
    assert _payload(mismatch)["error"] == "evidence_project_mismatch"


def test_edit_preserves_evidence_ownership_and_requires_revision() -> None:
    api = _Api()
    created = api.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        b'{"project_id":"project-1","asset_id":"asset-1","observation_type":"unknown"}',
    )
    observation_id = _payload(created)["item"]["id"]

    no_revision = api.dispatch(
        "PATCH",
        f"/api/v1/observations/{observation_id}",
        {},
        b'{"notes":"updated"}',
    )
    assert no_revision.status == 428

    immutable = api.dispatch(
        "PATCH",
        f"/api/v1/observations/{observation_id}",
        {"if-match": "1"},
        b'{"asset_id":"asset-2"}',
    )
    assert immutable.status == 400
    assert _payload(immutable)["error"] == "immutable_observation_field"

    updated = api.dispatch(
        "PATCH",
        f"/api/v1/observations/{observation_id}",
        {"if-match": "1"},
        b'{"notes":"updated","count":3,"observation_type":"organism"}',
    )
    assert updated.status == 200
    payload = _payload(updated)
    assert payload["revision"] == 2
    assert payload["item"]["asset_id"] == "asset-1"
    assert payload["item"]["notes"] == "updated"
    assert payload["item"]["count"] == 3

    stale = api.dispatch(
        "PATCH",
        f"/api/v1/observations/{observation_id}",
        {"if-match": "1"},
        b'{"notes":"stale"}',
    )
    assert stale.status == 409
    assert _payload(stale)["error"] == "revision_conflict"
