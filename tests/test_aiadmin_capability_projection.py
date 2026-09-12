from __future__ import annotations

from types import SimpleNamespace

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.web_capabilities import capability_payload


class AccessRepository:
    def __init__(self, identity: Identity, policies: tuple[Policy, ...]) -> None:
        self.identity = identity
        self._policies = policies
        self.audit: list[dict] = []

    def identities(self):
        return (self.identity,)

    def policies(self):
        return self._policies

    def role_ids(self, _subject_id: str, _organization_id: str, _project_id: str):
        return ()

    def contract(self, _contract_id: str):
        return None

    def append_audit(self, payload: dict) -> None:
        self.audit.append(payload)


def _policy(policy_id: str, action: str, resource_type: str) -> Policy:
    return Policy(
        policy_id=policy_id,
        name=policy_id,
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        source_id=policy_id,
        subject_id="ai-reader",
        actions=(action,),
        resource_types=(resource_type,),
        organization_id="local",
        purposes=("administration",),
    )


def _payload(*policies: Policy) -> dict[str, object]:
    identity = Identity("ai-reader", IdentityKind.USER, "AI Reader", "local")
    repository = AccessRepository(identity, policies)
    application = SimpleNamespace(
        _access_repository=repository,
        _decisions=PolicyDecisionService(repository),
    )
    return capability_payload(application, identity)


def test_ai_administration_read_does_not_imply_mutation_authority() -> None:
    payload = _payload(_policy("view-models", "view", "ai_model"))

    assert payload["pages"]["aiadmin"] is True
    assert payload["pages"]["administration"] is True
    assert payload["actions"]["aiadmin.models.manage"] is False
    assert payload["actions"]["aiadmin.providers.manage"] is False
    assert payload["actions"]["aiadmin.mcp.manage"] is False


def test_ai_administration_actions_follow_exact_resource_type() -> None:
    payload = _payload(
        _policy("view-models", "view", "ai_model"),
        _policy("edit-models", "edit", "ai_model"),
        _policy("edit-mcp", "edit", "mcp_server"),
    )

    assert payload["actions"]["aiadmin.manage"] is True
    assert payload["actions"]["aiadmin.models.manage"] is True
    assert payload["actions"]["aiadmin.mcp.manage"] is True
    assert payload["actions"]["aiadmin.providers.manage"] is False
