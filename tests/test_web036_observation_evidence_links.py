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
        self.items = {
            media_id: _MediaRecord(media_id)
            for media_id in ("asset-primary", "asset-2", "asset-3", "asset-shared")
        }
        self.record_calls: list[str] = []
        self.register_calls = 0

    def record(self, media_id: str):
        self.record_calls.append(media_id)
        return self.items.get(media_id)

    def register(self, *_args, **_kwargs):
        self.register_calls += 1
        raise AssertionError("observation evidence links must never clone/register evidence")


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


def _create(api: _Api, asset_id: str = "asset-primary") -> tuple[str, int]:
    response = api.dispatch(
        "POST",
        "/api/v1/observations",
        {},
        json.dumps(
            {
                "project_id": "project-1",
                "asset_id": asset_id,
                "observation_type": "unknown",
            }
        ).encode(),
    )
    assert response.status == 201
    payload = _payload(response)
    return payload["item"]["id"], payload["revision"]


def test_multiple_observations_can_share_one_existing_evidence_item() -> None:
    api = _Api()

    first_id, first_revision = _create(api, "asset-shared")
    second_id, second_revision = _create(api, "asset-shared")

    assert first_id != second_id
    assert first_revision == second_revision == 1
    assert api._media.record_calls == ["asset-shared", "asset-shared"]
    assert api._media.register_calls == 0


def test_one_observation_can_link_multiple_supporting_evidence_items() -> None:
    api = _Api()
    observation_id, revision = _create(api)

    second = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": str(revision)},
        b'{"asset_id":"asset-2"}',
    )
    assert second.status == 200
    second_payload = _payload(second)
    assert second_payload["revision"] == 2
    assert second_payload["item"]["asset_id"] == "asset-primary"
    assert second_payload["item"]["supporting_asset_ids"] == ["asset-2"]

    third = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "2"},
        b'{"asset_id":"asset-3"}',
    )
    assert third.status == 200
    third_payload = _payload(third)
    assert third_payload["revision"] == 3
    assert third_payload["item"]["supporting_asset_ids"] == ["asset-2", "asset-3"]
    assert api._media.register_calls == 0


def test_supporting_link_is_deduplicated_without_creating_a_revision() -> None:
    api = _Api()
    observation_id, _revision = _create(api)
    linked = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"asset-2"}',
    )
    assert linked.status == 200

    duplicate = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "2"},
        b'{"asset_id":"asset-2"}',
    )
    assert duplicate.status == 200
    payload = _payload(duplicate)
    assert payload["revision"] == 2
    assert payload["item"]["supporting_asset_ids"] == ["asset-2"]
    assert api._science.items[observation_id][1] == 2


def test_supporting_link_requires_visible_project_compatible_evidence() -> None:
    api = _Api()
    observation_id, _revision = _create(api)

    missing = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"missing"}',
    )
    assert missing.status == 404
    assert _payload(missing)["error"] == "evidence_not_found"

    api._media.items["asset-2"].project_id = "project-2"
    mismatch = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"asset-2"}',
    )
    assert mismatch.status == 409
    assert _payload(mismatch)["error"] == "evidence_project_mismatch"
    assert api._media.register_calls == 0


def test_primary_evidence_cannot_be_relinked_or_unlinked() -> None:
    api = _Api()
    observation_id, _revision = _create(api)

    relink = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"asset-primary"}',
    )
    assert relink.status == 409
    assert _payload(relink)["error"] == "evidence_already_primary"

    unlink = api.dispatch(
        "DELETE",
        f"/api/v1/observations/{observation_id}/evidence/asset-primary",
        {"if-match": "1"},
        b"",
    )
    assert unlink.status == 409
    assert _payload(unlink)["error"] == "cannot_unlink_primary_evidence"


def test_supporting_unlink_is_revision_safe_and_idempotent() -> None:
    api = _Api()
    observation_id, _revision = _create(api)
    linked = api.dispatch(
        "POST",
        f"/api/v1/observations/{observation_id}/evidence",
        {"if-match": "1"},
        b'{"asset_id":"asset-2"}',
    )
    assert linked.status == 200

    stale = api.dispatch(
        "DELETE",
        f"/api/v1/observations/{observation_id}/evidence/asset-2",
        {"if-match": "1"},
        b"",
    )
    assert stale.status == 409
    assert _payload(stale)["error"] == "revision_conflict"

    removed = api.dispatch(
        "DELETE",
        f"/api/v1/observations/{observation_id}/evidence/asset-2",
        {"if-match": "2"},
        b"",
    )
    assert removed.status == 200
    removed_payload = _payload(removed)
    assert removed_payload["revision"] == 3
    assert removed_payload["item"]["supporting_asset_ids"] == []

    absent = api.dispatch(
        "DELETE",
        f"/api/v1/observations/{observation_id}/evidence/asset-2",
        {"if-match": "3"},
        b"",
    )
    assert absent.status == 200
    assert _payload(absent)["revision"] == 3
    assert api._science.items[observation_id][1] == 3
