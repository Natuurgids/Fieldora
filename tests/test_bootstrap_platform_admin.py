from __future__ import annotations

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.bootstrap import platform_server_cli
from natureai_next.domain.access_control import (
    AccessRequest,
    IdentityKind,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository


def test_bootstrap_admin_gets_full_pbac_authority_with_explicit_deny_precedence(tmp_path) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    administration.create_organization("local", "Local")
    identity = administration.create_identity("Administrator", "local", IdentityKind.USER)
    administration.grant_role(identity.identity_id, "project-manager", "local")

    previous_repository = platform_server_cli._LAST_REPOSITORY
    previous_identity = platform_server_cli._LAST_IDENTITY
    try:
        platform_server_cli._LAST_REPOSITORY = repository
        platform_server_cli._LAST_IDENTITY = identity
        platform_server_cli._bootstrap_initial_operator(AccessAdministrationService)
    finally:
        platform_server_cli._LAST_REPOSITORY = previous_repository
        platform_server_cli._LAST_IDENTITY = previous_identity

    bootstrapped = repository.identity(identity.identity_id)
    assert bootstrapped is not None
    assert bootstrapped.attributes["platform_admin"] == "true"

    decisions = PolicyDecisionService(repository)
    request = AccessRequest(
        identity.identity_id,
        "arbitrary.admin.action",
        "arbitrary_platform_resource",
        "resource-1",
        "local",
        "",
        "administration",
    )
    assert decisions.decide(request).allowed is True

    administration.create_policy(
        name="Explicit bootstrap-admin deny remains authoritative",
        effect=PolicyEffect.DENY,
        source=PolicySource.DIRECT,
        subject_id=identity.identity_id,
        actions=("arbitrary.admin.action",),
        resource_types=("arbitrary_platform_resource",),
        organization_id="local",
        purposes=("administration",),
    )
    assert decisions.decide(request).allowed is False
