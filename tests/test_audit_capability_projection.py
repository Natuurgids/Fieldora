from __future__ import annotations

import json
from types import SimpleNamespace

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi


class AccessRepository:
    def __init__(self, identity: Identity, policies: tuple[Policy, ...]) -> None:
        self.identity = identity
        self._policies = policies
        self.audit: list[dict] = []

    def identities(self):
        return (self.identity,)

    def policies(self):
        return self._policies

    def role_ids(self, subject_id: str, organization_id: str, project_id: str):
        return ()

    def contract(self, _contract_id: str):
        return None

    def append_audit(self, payload: dict) -> None:
        self.audit.append(payload)


def _audit_policy(effect: PolicyEffect = PolicyEffect.ALLOW) -> Policy:
    return Policy(
        policy_id=f"audit-{effect.value}",
        name=f"audit-{effect.value}",
        effect=effect,
        source=PolicySource.DIRECT,
        source_id=f"audit-{effect.value}",
        subject_id="user-1",
        actions=("view_audit",),
        resource_types=("security_audit",),
        organization_id="local",
        purposes=("administration",),
    )


def _application(policies: tuple[Policy, ...]):
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    repository = AccessRepository(identity, policies)
    return SimpleNamespace(
        _access_repository=repository,
        _decisions=PolicyDecisionService(repository),
        _identity=lambda _headers: ("test-token", identity),
    )


def _capabilities(application) -> dict[str, object]:
    response = BrowserFunctionalityFieldoraApi._web_capabilities(application, {})
    assert response.status == 200
    return json.loads(response.body)


def test_audit_grant_projects_audit_and_administration_navigation() -> None:
    payload = _capabilities(_application((_audit_policy(),)))

    assert payload["pages"]["audit"] is True
    assert payload["pages"]["administration"] is True
    assert payload["default_deny"] is True


def test_audit_default_deny_hides_audit_navigation() -> None:
    payload = _capabilities(_application(()))

    assert payload["pages"]["audit"] is False
    assert payload["pages"]["administration"] is False


def test_explicit_audit_deny_overrides_audit_grant() -> None:
    payload = _capabilities(
        _application((_audit_policy(), _audit_policy(PolicyEffect.DENY)))
    )

    assert payload["pages"]["audit"] is False
    assert payload["pages"]["administration"] is False