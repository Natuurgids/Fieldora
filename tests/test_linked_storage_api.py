from __future__ import annotations

import json

from natureai_next.domain.access_control import AccessDecision, Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_api import LinkedStorageApiMixin
from natureai_next.server.postgres_linked_preview_store import LinkedPreviewObject
from natureai_next.server.postgres_linked_storage import ServerLinkedMedia
from natureai_next.server.storage_exchange import PreviewState, StorageObjectState


class _Decisions:
    def __init__(self, denied_media_id: str = "") -> None:
        self.denied_media_id = denied_media_id
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return AccessDecision(request.resource_id != self.denied_media_id, "test")


class _Repository:
    def __init__(self, records: tuple[ServerLinkedMedia, ...]) -> None:
        self.records = records
        self.preview_requests: list[dict] = []
        self.previews: dict[str, LinkedPreviewObject] = {}

    def browse(self, organization_id: str, storage_id: str, prefix: str = "", limit: int = 200):
        return tuple(
            record
            for record in self.records
            if record.organization_id == organization_id
            and record.storage_id == storage_id
            and (not prefix or record.relative_path.startswith(prefix.rstrip("/") + "/"))
        )[:limit]

    def media(self, media_id: str):
        return next((record for record in self.records if record.media_id == media_id), None)

    def request_preview(self, **kwargs):
        self.preview_requests.append(kwargs)
        return True

    def preview(self, media_id: str):
        return self.previews.get(media_id)


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(LinkedStorageApiMixin, _BaseApi):
    def __init__(self, records: tuple[ServerLinkedMedia, ...], *, denied_media_id: str = "") -> None:
        self._linked_storage = _Repository(records)
        self._decisions = _Decisions(denied_media_id)
        self.identity = Identity("researcher-1", IdentityKind.USER, "Researcher", "org-1")

    def _identity(self, headers):
        if headers.get("authorization") != "Bearer good-token":
            from natureai_next.application.authentication import AuthenticationFailed

            raise AuthenticationFailed("invalid token")
        return "good-token", self.identity


def _record(media_id: str, *, organization_id: str = "org-1", project_id: str = "project-1"):
    return ServerLinkedMedia(
        media_id=media_id,
        storage_id="storage-1",
        object_id=f"opaque-{media_id}",
        organization_id=organization_id,
        relative_path=f"Amazon/day-01/{media_id}.jpg",
        filename=f"{media_id}.jpg",
        mime_type="image/jpeg",
        size_bytes=1234,
        modified_ns=123456,
        object_state=StorageObjectState.AVAILABLE,
        sha256="a" * 64,
        thumbnail_state=PreviewState.MISSING,
        thumbnail_etag="",
        project_id=project_id,
        metadata={"camera": "trap-7"},
    )


def _headers():
    return {"authorization": "Bearer good-token", "x-fieldora-purpose": "research"}


def test_browse_filters_pbac_and_never_discloses_storage_service_fields() -> None:
    api = _Api((_record("media-1"), _record("media-denied")), denied_media_id="media-denied")
    response = api.dispatch(
        "GET",
        "/api/v1/linked-storage/browse?storage_id=storage-1&prefix=Amazon/day-01",
        _headers(),
        b"",
    )
    payload = json.loads(response.body)

    assert response.status == 200
    assert payload["count"] == 1
    assert payload["items"][0]["media_id"] == "media-1"
    assert "object_id" not in payload["items"][0]
    assert "root_alias" not in payload["items"][0]
    assert "service_id" not in payload["items"][0]
    assert api._decisions.requests[0].resource_type == "asset"
    assert api._decisions.requests[0].project_id == "project-1"


def test_preview_request_queues_only_authorized_same_organization_media() -> None:
    api = _Api(
        (
            _record("media-1"),
            _record("media-denied"),
            _record("foreign", organization_id="org-2"),
        ),
        denied_media_id="media-denied",
    )
    response = api.dispatch(
        "POST",
        "/api/v1/linked-storage/previews",
        _headers(),
        json.dumps(
            {
                "media_ids": ["media-1", "media-denied", "foreign"],
                "priority": 900,
                "reason": "opened-detail",
            }
        ).encode(),
    )
    payload = json.loads(response.body)

    assert response.status == 202
    assert payload["queued_media_ids"] == ["media-1"]
    assert payload["unavailable_media_ids"] == ["media-denied", "foreign"]
    assert api._linked_storage.preview_requests == [
        {
            "media_id": "media-1",
            "organization_id": "org-1",
            "priority": 900,
            "reason": "opened-detail",
            "requested_by": "researcher-1",
        }
    ]


def test_thumbnail_returns_only_managed_derivative_after_pbac() -> None:
    api = _Api((_record("media-1"), _record("media-denied")), denied_media_id="media-denied")
    payload = b"\xff\xd8managed-thumbnail\xff\xd9"
    digest = "b" * 64
    api._linked_storage.previews["media-1"] = LinkedPreviewObject(
        "media-1", "image/jpeg", digest, payload
    )
    api._linked_storage.previews["media-denied"] = LinkedPreviewObject(
        "media-denied", "image/jpeg", digest, payload
    )

    response = api.dispatch(
        "GET",
        "/api/v1/linked-storage/thumbnail?media_id=media-1",
        _headers(),
        b"",
    )
    assert response.status == 200
    assert response.body == payload
    assert response.content_type == "image/jpeg"
    assert ("ETag", f'"{digest}"') in response.headers
    assert all("storage" not in name.casefold() for name, _value in response.headers)

    denied = api.dispatch(
        "GET",
        "/api/v1/linked-storage/thumbnail?media_id=media-denied",
        _headers(),
        b"",
    )
    assert denied.status == 404


def test_linked_storage_requires_authentication() -> None:
    api = _Api((_record("media-1"),))
    response = api.dispatch(
        "GET",
        "/api/v1/linked-storage/browse?storage_id=storage-1",
        {},
        b"",
    )
    assert response.status == 401
