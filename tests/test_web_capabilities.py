from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from urllib.request import Request, urlopen

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.http import handler_for
from natureai_next.server.web_capabilities import (
    capability_payload,
    patch_zero_trust_web_response,
    project_help_response,
)


class AccessRepository:
    def __init__(
        self,
        identity: Identity,
        policies: tuple[Policy, ...],
        project_roles: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.identity = identity
        self._policies = policies
        self.project_roles = project_roles or {}
        self.audit: list[dict] = []

    def identities(self):
        return (self.identity,)

    def policies(self):
        return self._policies

    def role_ids(self, subject_id: str, organization_id: str, project_id: str):
        if subject_id != self.identity.identity_id:
            return ()
        return self.project_roles.get(project_id, ())

    def contract(self, _contract_id: str):
        return None

    def append_audit(self, payload: dict) -> None:
        self.audit.append(payload)


def policy(
    policy_id: str,
    *,
    effect: PolicyEffect = PolicyEffect.ALLOW,
    subject_id: str = "user-1",
    role_id: str = "",
    actions: tuple[str, ...] = ("view",),
    resource_types: tuple[str, ...] = ("project",),
    project_id: str = "",
    purpose: str = "research",
) -> Policy:
    return Policy(
        policy_id=policy_id,
        name=policy_id,
        effect=effect,
        source=PolicySource.DIRECT,
        source_id=policy_id,
        subject_id=subject_id,
        role_id=role_id,
        actions=actions,
        resource_types=resource_types,
        organization_id="local",
        project_id=project_id,
        purposes=(purpose,),
    )


def application(repository: AccessRepository):
    return SimpleNamespace(
        _access_repository=repository,
        _decisions=PolicyDecisionService(repository),
        _identity=lambda _headers: ("test-token", repository.identity),
    )


def test_capabilities_fail_closed_and_explicit_deny_hides_projects() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (
            policy("allow-project"),
            policy("deny-project", effect=PolicyEffect.DENY),
            policy("allow-library", resource_types=("asset",)),
        ),
    )

    payload = capability_payload(application(repository), identity)

    assert payload["default_deny"] is True
    assert payload["pages"]["projects"] is False
    assert payload["pages"]["library"] is True
    assert payload["pages"]["administration"] is False
    assert payload["pages"]["operator"] is False


def test_operator_capability_uses_real_infrastructure_pbac_vocabulary() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (
            policy(
                "operator-reader",
                actions=("infrastructure.view",),
                resource_types=("infrastructure",),
                purpose="administration",
            ),
        ),
    )

    payload = capability_payload(application(repository), identity)

    assert payload["pages"]["operator"] is True
    assert payload["pages"]["administration"] is True


def test_operator_explicit_deny_overrides_real_infrastructure_grant() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (
            policy(
                "allow-operator",
                actions=("infrastructure.view",),
                resource_types=("infrastructure",),
                purpose="administration",
            ),
            policy(
                "deny-operator",
                effect=PolicyEffect.DENY,
                actions=("infrastructure.view",),
                resource_types=("infrastructure",),
                purpose="administration",
            ),
        ),
    )

    payload = capability_payload(application(repository), identity)

    assert payload["pages"]["operator"] is False
    assert payload["pages"]["administration"] is False


def test_review_capability_uses_real_review_case_pbac_vocabulary() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (
            policy(
                "review-reader",
                actions=("view_review",),
                resource_types=("review_case",),
            ),
        ),
    )

    payload = capability_payload(application(repository), identity)

    assert payload["pages"]["intake-review"] is True
    assert payload["pages"]["administration"] is True


def test_project_scoped_role_reveals_workspace_but_not_scope_identifier() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (
            policy(
                "project-member",
                subject_id="",
                role_id="scientist",
                project_id="secret-project-id",
            ),
        ),
        project_roles={"secret-project-id": ("scientist",)},
    )

    payload = capability_payload(application(repository), identity)

    assert payload["pages"]["projects"] is True
    assert payload["pages"]["research"] is True
    assert "secret-project-id" not in json.dumps(payload)


def test_help_projection_removes_denied_workspace_topics_and_direct_lookup() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(
        identity,
        (policy("allow-library", resource_types=("asset",)),),
    )
    app = application(repository)
    catalogue = ApiResponse.json(
        200,
        {
            "items": [
                {"topic_id": "quick-start", "title": "Quick start", "workspace": "home"},
                {"topic_id": "library", "title": "Library", "workspace": "library"},
                {"topic_id": "admin", "title": "Administration", "workspace": "administration"},
                {"topic_id": "operator", "title": "Operator", "workspace": "operator"},
                {"topic_id": "accessibility", "title": "Accessibility", "workspace": "help"},
            ]
        },
    )

    projected = project_help_response(app, "/api/v1/help", {}, catalogue)
    items = json.loads(projected.body)["items"]

    assert [item["topic_id"] for item in items] == [
        "quick-start",
        "library",
        "accessibility",
    ]
    denied = project_help_response(
        app,
        "/api/v1/help/operator",
        {},
        ApiResponse.json(
            200,
            {
                "topic_id": "operator",
                "title": "Operator",
                "workspace": "operator",
                "content": "hidden",
            },
        ),
    )
    assert denied.status == 404
    assert json.loads(denied.body) == {"error": "help_topic_not_found"}


def test_zero_trust_project_list_fails_closed_under_contract_runtime() -> None:
    response = patch_zero_trust_web_response(
        "/app.js",
        ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "if(list?.items)return Array.from(list.items()||[]);" in script
    assert "return window.FieldoraModuleContracts?[]:projects;" in script
    assert "await list.refresh();" in script
    assert "const items=await list.refresh();projects=items.map(item=>({...item}));" not in script
    assert "else if(!window.FieldoraModuleContracts){" in script


def test_http_handler_writes_immutable_tuple_headers() -> None:
    class Application:
        def dispatch(self, method, target, headers, body):
            assert method == "GET"
            assert target == "/api/v1/test"
            return ApiResponse(
                200,
                b"ok",
                "text/plain; charset=utf-8",
                (("X-Fieldora-Test", "tuple-header"),),
            )

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(Application()))  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/v1/test") as response:
            assert response.read() == b"ok"
            assert response.headers["X-Fieldora-Test"] == "tuple-header"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_handler_normalizes_browser_authentication_headers() -> None:
    class Application:
        def dispatch(self, method, target, headers, body):
            assert method == "GET"
            assert target == "/api/v1/me"
            assert headers["authorization"] == "Bearer browser-session-token"
            assert headers["cookie"] == "fieldora_session=cookie-token"
            assert headers["x-fieldora-web-session"] == "1"
            assert "Authorization" not in headers
            return ApiResponse.json(200, {"authenticated": True})

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(Application()))  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/me",
            headers={
                "Authorization": "Bearer browser-session-token",
                "Cookie": "fieldora_session=cookie-token",
                "X-Fieldora-Web-Session": "1",
            },
        )
        with urlopen(request) as response:
            assert json.loads(response.read()) == {"authenticated": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
