from __future__ import annotations

import hashlib
import json
from pathlib import Path

from natureai_next.domain.access_control import (
    AccessDecision,
    AccessRequest,
    Identity,
    IdentityKind,
    Policy,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import (
    BrowserFunctionalityFieldoraApi,
    _session_cookie,
    _session_cookie_header,
)
from natureai_next.server.media import GovernedMediaStore, MediaRecord


class _Authentication:
    def __init__(self, identity: Identity) -> None:
        self.identity = identity

    def authenticate(self, token: str) -> Identity:
        assert token == "browser-token"
        return self.identity


class _Decisions:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.requests: list[AccessRequest] = []

    def decide(self, request: AccessRequest) -> AccessDecision:
        self.requests.append(request)
        return AccessDecision(self.allowed, "test")


class _Science:
    def __init__(self) -> None:
        self.writes: list[tuple[str, dict, int | None]] = []

    def put(self, collection: str, record: dict, expected: int | None) -> int:
        self.writes.append((collection, record, expected))
        return 1


class _AccessRepository:
    def __init__(self) -> None:
        self.saved_policies: list[Policy] = []

    def put_policy(self, policy: Policy) -> None:
        self.saved_policies.append(policy)


def _api(
    *, allowed: bool = True, access_repository: _AccessRepository | None = None
) -> tuple[BrowserFunctionalityFieldoraApi, _Decisions, _Science]:
    identity = Identity(
        "admin-1",
        IdentityKind.USER,
        "Administrator",
        "local",
        attributes={"platform_admin": "true"},
    )
    api = BrowserFunctionalityFieldoraApi.__new__(BrowserFunctionalityFieldoraApi)
    api._authentication = _Authentication(identity)
    api._oidc = None
    api._access_repository = access_repository
    decisions = _Decisions(allowed)
    science = _Science()
    api._decisions = decisions
    api._science = science
    return api, decisions, science


def _upload_and_link(
    api: BrowserFunctionalityFieldoraApi,
    store: GovernedMediaStore,
    payload: bytes,
    project_id: str,
) -> MediaRecord:
    digest = hashlib.sha256(payload).hexdigest()
    upload = store.begin_upload(
        "admin-1",
        "local",
        project_id,
        "shared-evidence.bin",
        "application/octet-stream",
        len(payload),
        digest,
    )
    record = store.append_upload(upload, 0, payload)
    assert isinstance(record, MediaRecord)
    api._link_completed_upload(
        upload,
        {"x-fieldora-purpose": "research"},
        ApiResponse.json(201, {"media_id": record.media_id}),
    )
    return record


def test_browser_session_cookie_is_secure_httponly_and_strict() -> None:
    header = _session_cookie_header("browser-token")
    assert "fieldora_session=browser-token" in header
    assert "Path=/api/v1/" in header
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "SameSite=Strict" in header
    assert _session_cookie("other=x; fieldora_session=browser-token") == "browser-token"


def test_project_creation_uses_organization_level_create_permission() -> None:
    api, decisions, science = _api()
    response = api._create_project(
        {
            "authorization": "Bearer browser-token",
            "x-fieldora-purpose": "research",
        },
        json.dumps({"id": "project-new", "name": "New Project"}).encode(),
    )

    assert response.status == 201
    assert len(decisions.requests) == 1
    request = decisions.requests[0]
    assert request.action == "create"
    assert request.resource_type == "project"
    assert request.organization_id == "local"
    assert request.project_id == ""
    assert science.writes[0][0] == "projects"
    assert science.writes[0][1]["owner_id"] == "admin-1"


def test_project_creator_receives_project_scoped_workspace_permission() -> None:
    repository = _AccessRepository()
    api, _decisions, _science = _api(access_repository=repository)

    response = api._create_project(
        {"authorization": "Bearer browser-token", "x-fieldora-purpose": "research"},
        json.dumps({"id": "project-new", "name": "New Project"}).encode(),
    )

    assert response.status == 201
    assert len(repository.saved_policies) == 1
    policy = repository.saved_policies[0]
    assert policy.subject_id == "admin-1"
    assert policy.organization_id == "local"
    assert policy.project_id == "project-new"
    assert "phase" in policy.resource_types
    assert "task" in policy.resource_types
    assert "edit" in policy.actions
    assert policy.purposes == ("research",)


def test_project_creation_remains_default_denied_without_policy() -> None:
    api, decisions, science = _api(allowed=False)
    response = api._create_project(
        {"authorization": "Bearer browser-token"},
        json.dumps({"id": "project-new", "name": "New Project"}).encode(),
    )

    assert response.status == 403
    assert decisions.requests[0].action == "create"
    assert science.writes == []


def test_canonical_media_is_project_scoped_by_association(tmp_path: Path) -> None:
    api, _decisions, _science = _api()
    store = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "objects")
    api._media = store
    payload = b"one canonical evidence object in two projects"
    headers = {
        "authorization": "Bearer browser-token",
        "x-fieldora-purpose": "research",
    }

    first = _upload_and_link(api, store, payload, "project-a")
    second = _upload_and_link(api, store, payload, "project-b")

    assert second.media_id == first.media_id
    assert len(store.records("local")) == 1
    links = store.associations.links(first.media_id, "local")
    assert [(link.association_type, link.target_id) for link in links] == [
        ("project", "project-a"),
        ("project", "project-b"),
    ]

    for project_id in ("project-a", "project-b"):
        listing = api._associated_media_list_response(
            f"project_id={project_id}", headers
        )
        assert listing.status == 200
        listing_payload = json.loads(listing.body)
        assert listing_payload["count"] == 1
        assert listing_payload["items"][0]["media_id"] == first.media_id
        assert listing_payload["items"][0]["project_id"] == project_id

        download = api._associated_media_response(
            first.media_id, "GET", f"project_id={project_id}", headers
        )
        assert download.status == 200
        assert download.body == payload

    unlinked_listing = api._associated_media_list_response(
        "project_id=project-c", headers
    )
    assert unlinked_listing.status == 200
    assert json.loads(unlinked_listing.body) == {"items": [], "count": 0}
    assert (
        api._associated_media_response(
            first.media_id, "GET", "project_id=project-c", headers
        ).status
        == 404
    )


def test_browser_functionality_does_not_put_session_tokens_in_media_urls() -> None:
    source = Path("src/natureai_next/server/browser_functionality_web.py").read_text(
        encoding="utf-8"
    )
    assert "fieldora-session" not in source
    assert "access_token=" not in source
    assert "Authorization" not in source
    assert "/api/v1/media/" in source


def test_directory_intake_waits_for_validation_before_processing() -> None:
    source = Path("src/natureai_next/server/directory_intake_web.py").read_text(
        encoding="utf-8"
    )
    validation = source.index("await waitForValidation(sid,files.length)")
    processing = source.index("/process`,{method:\"POST\"")
    assert validation < processing
    assert "validated_with_rejections" in source
    assert "submission_not_validated" not in source
