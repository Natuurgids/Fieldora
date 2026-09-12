from __future__ import annotations

from natureai_next.bootstrap import platform_server_cli
from natureai_next.domain.access_control import Identity, IdentityKind, PolicyEffect, PolicySource


class _Repository:
    def __init__(self) -> None:
        self.identities: list[Identity] = []

    def put_identity(self, identity: Identity) -> None:
        self.identities.append(identity)


class _Administration:
    policies: list[dict[str, object]] = []
    roles: list[tuple[str, str, str]] = []

    def __init__(self, repository: _Repository) -> None:
        self.repository = repository

    def grant_role(self, identity_id: str, role_id: str, organization_id: str) -> None:
        type(self).roles.append((identity_id, role_id, organization_id))

    def create_policy(self, **values: object) -> None:
        type(self).policies.append(values)


def test_initial_operator_gets_narrow_ai_administration_policy() -> None:
    repository = _Repository()
    identity = Identity("admin-1", IdentityKind.USER, "Administrator", "local")
    previous_repository = platform_server_cli._LAST_REPOSITORY
    previous_identity = platform_server_cli._LAST_IDENTITY
    _Administration.policies = []
    _Administration.roles = []
    try:
        platform_server_cli._LAST_REPOSITORY = repository
        platform_server_cli._LAST_IDENTITY = identity
        platform_server_cli._bootstrap_initial_operator(_Administration)
    finally:
        platform_server_cli._LAST_REPOSITORY = previous_repository
        platform_server_cli._LAST_IDENTITY = previous_identity

    ai_policy = next(
        policy
        for policy in _Administration.policies
        if policy["name"] == "Initial AI and integration administrator"
    )
    assert ai_policy["effect"] is PolicyEffect.ALLOW
    assert ai_policy["source"] is PolicySource.ROLE
    assert ai_policy["role_id"] == "platform-operator"
    assert ai_policy["actions"] == ("view", "edit")
    assert ai_policy["resource_types"] == (
        "ai_provider",
        "ai_model",
        "mcp_server",
        "connector",
        "reference_value",
    )
    assert ai_policy["organization_id"] == "local"
    assert ai_policy["purposes"] == ("administration",)
    assert "*" not in ai_policy["actions"]
    assert "*" not in ai_policy["resource_types"]
    assert _Administration.roles == [("admin-1", "platform-operator", "local")]
    assert repository.identities[-1].attributes["platform_admin"] == "true"
