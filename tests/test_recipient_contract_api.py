from __future__ import annotations

from dataclasses import dataclass

from natureai_next.domain.access_control import AccessDecision, Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.recipient_contract_api import RecipientContractFieldoraApi


@dataclass(frozen=True)
class _MediaRecord:
    media_id: str = "asset-1"
    relative_path: str = "aa/asset-1.jpg"
    organization_id: str = "source-org"
    project_id: str = "source-project"
    mime_type: str = "image/jpeg"
    size_bytes: int = 4
    sha256: str = "a" * 64


class _Media:
    def __init__(self) -> None:
        self.item = _MediaRecord()

    def record(self, media_id: str):
        return self.item if media_id == self.item.media_id else None

    def read_range(self, record, start: int, end: int) -> bytes:
        assert record is self.item
        return b"data"[start : end + 1]


class _Barriers:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def allows_asset(self, asset_id: str, *, organization_id: str, project_ids=()) -> bool:
        assert asset_id == "asset-1"
        assert organization_id == "recipient-org"
        assert project_ids == ("recipient-project",)
        return self.allowed

    def candidate_shared_assets(self, *, organization_id: str, project_ids=(), limit: int = 500):
        assert organization_id == "recipient-org"
        assert project_ids == ("recipient-project",)
        assert limit >= 1
        return ("asset-1",)


class _Decisions:
    def __init__(self) -> None:
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        allowed = (
            request.organization_id == "recipient-org"
            and request.project_id == "recipient-project"
            and request.resource_id == "asset-1"
        )
        return AccessDecision(allowed, "recipient scope" if allowed else "not recipient scope")


class _RecipientApi(RecipientContractFieldoraApi):
    def __init__(self, *, barrier_allowed: bool = True) -> None:
        self._barriers = _Barriers(barrier_allowed)
        self._media = _Media()
        self._decisions = _Decisions()
        self.identity = Identity(
            "recipient-user",
            IdentityKind.USER,
            "Recipient",
            "recipient-org",
        )

    def _identity(self, headers):
        return "token", self.identity

    def _project_memberships(self, identity_id: str):
        assert identity_id == self.identity.identity_id
        return ("recipient-project",)


def test_shared_download_preserves_source_ownership_and_uses_recipient_scope() -> None:
    api = _RecipientApi()

    response = api._shared_media_response(
        "asset-1",
        "GET",
        {"x-fieldora-purpose": "research"},
    )

    assert response.status == 200
    assert response.body == b"data"
    headers = dict(response.headers)
    assert headers["X-Fieldora-Source-Organization"] == "source-org"
    assert headers["X-Fieldora-Source-Project"] == "source-project"
    assert headers["X-Fieldora-Shared-Via-Contract"] == "true"
    assert any(
        request.organization_id == "recipient-org"
        and request.project_id == "recipient-project"
        for request in api._decisions.requests
    )
    assert all(request.organization_id != "source-org" for request in api._decisions.requests)


def test_shared_download_is_hidden_when_source_contract_does_not_target_recipient() -> None:
    api = _RecipientApi(barrier_allowed=False)

    response = api._shared_media_response("asset-1", "GET", {})

    assert response.status == 404


def test_shared_asset_list_marks_source_without_transferring_ownership() -> None:
    api = _RecipientApi()
    local = ApiResponse.json(200, {"items": [], "count": 0})

    response = api._augment_media_list(local, "limit=25", {})

    assert response.status == 200
    import json

    item = json.loads(response.body)["items"][0]
    assert item["media_id"] == "asset-1"
    assert item["source_organization_id"] == "source-org"
    assert item["source_project_id"] == "source-project"
    assert item["shared_via_contract"] is True
