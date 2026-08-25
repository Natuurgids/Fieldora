from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from urllib.request import urlopen

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
from natureai_next.server.web_capabilities import capability_payload


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
