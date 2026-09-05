from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.original_derivative_api import OriginalDerivativeApiMixin


@dataclass
class _Identity:
    identity_id: str = "researcher-1"
    organization_id: str = "org-1"


class _Science:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, tuple[dict, int]]] = {}

    def records(self, collection: str):
        return tuple(
            dict(item) for item, _revision in self.items.get(collection, {}).values()
        )

    def put(self, collection: str, record: dict, expected_revision: int | None):
        bucket = self.items.setdefault(collection, {})
        record_id = str(record["id"])
        current = bucket.get(record_id)
        revision = 0 if current is None else current[1]
        if expected_revision is not None and revision != expected_revision:
            raise ValueError("revision_conflict")
        revision += 1
        bucket[record_id] = (dict(record), revision)
        return revision


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


class _Decisions:
    def __init__(self) -> None:
        self.allowed = True
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return _Decision(self.allowed)


class _Base:
    def __init__(self, media: GovernedMediaStore) -> None:
        self._media = media
        self._science = _Science()
        self._decisions = _Decisions()
        self.identity = _Identity()

    def _identity(self, _headers):
        return "token", self.identity

    def dispatch(self, method, target, _headers, _body):
        if method == "GET" and target.endswith("/detail"):
            media_id = target.split("/")[-2]
            record = self._media.record(media_id)
            if record is None:
                return ApiResponse.json(404, {"error": "not_found"})
            return ApiResponse.json(
                200,
                {
                    "item": {
                        "media_id": record.media_id,
                        "mime_type": record.mime_type,
                        "size_bytes": record.size_bytes,
                        "sha256": record.sha256,
                    },
                    "storage": {"storage_policy": "managed"},
                    "associations": [],
                },
            )
        if method == "GET" and target == "/app.js":
            return ApiResponse(200, b"window.baseApp=true;", "text/javascript")
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(OriginalDerivativeApiMixin, _Base):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def _fixture(tmp_path):
    source = tmp_path / "original.tif"
    source.write_bytes(b"governed-original-pixels")
    media = GovernedMediaStore(tmp_path / "media.db", tmp_path / "objects")
    original = media.register(source, "org-1", "project-1")
    return _Api(media), original


def _derivative_body(original, **overrides) -> bytes:
    payload = {
        "kind": "thumbnail",
        "mime_type": "image/jpeg",
        "size_bytes": 123,
        "sha256": "b" * 64,
        "source_sha256": original.sha256,
        "label": "512 px governed preview",
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_derivative_registration_never_mutates_governed_original(tmp_path) -> None:
    api, original = _fixture(tmp_path)
    before_record = asdict(api._media.record(original.media_id))
    before_bytes = api._media.read_range(original, 0, original.size_bytes - 1)

    response = api.dispatch(
        "POST",
        f"/api/v1/media/{original.media_id}/derivatives",
        {"x-fieldora-purpose": "research"},
        _derivative_body(original),
    )

    assert response.status == 201
    payload = _payload(response)
    assert payload["item"]["source_media_id"] == original.media_id
    assert payload["item"]["source_sha256"] == original.sha256
    assert payload["item"]["sha256"] == "b" * 64
    assert payload["item"]["derivative_id"] != original.media_id
    assert payload["original_mutated"] is False
    assert "organization_id" not in payload["item"]
    assert "created_by_identity_id" not in payload["item"]

    after = api._media.record(original.media_id)
    assert asdict(after) == before_record
    assert api._media.read_range(after, 0, after.size_bytes - 1) == before_bytes


def test_derivative_registration_is_bound_to_current_original_hash(tmp_path) -> None:
    api, original = _fixture(tmp_path)
    response = api.dispatch(
        "POST",
        f"/api/v1/media/{original.media_id}/derivatives",
        {},
        _derivative_body(original, source_sha256="a" * 64),
    )
    assert response.status == 409
    assert _payload(response)["error"] == "original_identity_changed"
    assert api._science.records("server_media_derivatives") == ()


def test_caller_cannot_forge_derivative_identity_or_source(tmp_path) -> None:
    api, original = _fixture(tmp_path)
    response = api.dispatch(
        "POST",
        f"/api/v1/media/{original.media_id}/derivatives",
        {},
        _derivative_body(original, id="caller-id"),
    )
    assert response.status == 400
    assert _payload(response)["error"] == "invalid_derivative"


def test_derivative_list_and_detail_keep_original_authoritative(tmp_path) -> None:
    api, original = _fixture(tmp_path)
    created = api.dispatch(
        "POST",
        f"/api/v1/media/{original.media_id}/derivatives",
        {},
        _derivative_body(original),
    )
    assert created.status == 201

    listed = api.dispatch(
        "GET", f"/api/v1/media/{original.media_id}/derivatives", {}, b""
    )
    assert listed.status == 200
    listed_payload = _payload(listed)
    assert listed_payload["source"]["artifact_role"] == "governed_original"
    assert listed_payload["source"]["sha256"] == original.sha256
    assert len(listed_payload["items"]) == 1
    assert listed_payload["original_mutated"] is False

    detail = api.dispatch(
        "GET", f"/api/v1/media/{original.media_id}/detail", {}, b""
    )
    assert detail.status == 200
    detail_payload = _payload(detail)
    assert detail_payload["item"]["artifact_role"] == "governed_original"
    assert detail_payload["derivatives"][0]["kind"] == "thumbnail"
    assert detail_payload["derivative_contract"] == {
        "original_authoritative": True,
        "derivatives_replace_original": False,
        "lineage_hash": original.sha256,
    }


def test_derivative_routes_are_fail_closed_under_pbac(tmp_path) -> None:
    api, original = _fixture(tmp_path)
    api._decisions.allowed = False

    hidden = api.dispatch(
        "GET", f"/api/v1/media/{original.media_id}/derivatives", {}, b""
    )
    assert hidden.status == 404

    forbidden = api.dispatch(
        "POST",
        f"/api/v1/media/{original.media_id}/derivatives",
        {},
        _derivative_body(original),
    )
    assert forbidden.status == 403
    assert api._science.records("server_media_derivatives") == ()
    assert [(request.action, request.resource_type) for request in api._decisions.requests] == [
        ("view", "asset"),
        ("derive", "asset"),
    ]
