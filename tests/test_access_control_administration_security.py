from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.application.access_control import AccessAdministrationService, AccessDenied
from natureai_next.domain.access_control import Identity, IdentityKind, Policy, PolicyEffect, PolicySource
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.infrastructure.subsystems.access_control import ACCESS_CONTROL_MIGRATIONS
from natureai_next.infrastructure.subsystems.base import MigrationRunner


def _repository(path: Path) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(path)
    with repository.connection() as connection:
        MigrationRunner(ACCESS_CONTROL_MIGRATIONS, "security-test").apply(connection)
    return repository


def _authorize(repository: SqliteAccessControlRepository, actor_id: str, resource_type: str) -> None:
    repository.put_identity(Identity(actor_id, IdentityKind.USER, "Administrator", "org-1"))
    repository.put_policy(
        Policy(
            policy_id=f"admin-{resource_type}",
            name=f"Administer {resource_type}",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id=actor_id,
            subject_id=actor_id,
            role_id="",
            actions=("administer",),
            resource_types=(resource_type,),
            organization_id="org-1",
            purposes=("access_control_administration",),
        )
    )


@pytest.mark.parametrize(
    ("resource_type", "mutation"),
    (
        ("access_organization", lambda service: service.create_organization("org-1", "Org")),
        ("access_identity", lambda service: service.create_identity("User", "org-1", IdentityKind.USER)),
        ("access_group_membership", lambda service: service.add_group_member("group-1", "member-1")),
        ("access_role_assignment", lambda service: service.grant_role("member-1", "researcher", "org-1")),
        ("access_contract", lambda service: service.create_contract("Contract", "org-1", "2026-01-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00")),
        ("access_policy", lambda service: service.create_policy(name="Policy", effect=PolicyEffect.DENY, source=PolicySource.DIRECT, subject_id="member-1", actions=("view",), resource_types=("asset",), organization_id="org-1")),
    ),
)
def test_mutations_fail_closed_without_authenticated_actor(
    tmp_path: Path, resource_type: str, mutation,
) -> None:
    repository = _repository(tmp_path / "access.sqlite3")
    service = AccessAdministrationService(repository)

    with pytest.raises(AccessDenied, match="authenticated actor"):
        mutation(service)


def test_authorized_actor_can_create_identity(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "access.sqlite3")
    _authorize(repository, "admin-1", "access_identity")

    identity = AccessAdministrationService(repository, actor_id="admin-1").create_identity(
        "Researcher", "org-1", IdentityKind.USER
    )

    assert identity.display_name == "Researcher"


def test_actor_without_administration_policy_is_denied(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "access.sqlite3")
    repository.put_identity(Identity("user-1", IdentityKind.USER, "User", "org-1"))

    with pytest.raises(AccessDenied):
        AccessAdministrationService(repository, actor_id="user-1").create_identity(
            "Escalated", "org-1", IdentityKind.USER
        )


def test_actor_cannot_self_provision_security_install_policy(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "access.sqlite3")
    repository.put_identity(Identity("user-1", IdentityKind.USER, "User", "org-1"))
    service = AccessAdministrationService(repository, actor_id="user-1")

    with pytest.raises(AccessDenied):
        service.create_policy(
            name="Self provision Security Install",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            subject_id="user-1",
            actions=("install",),
            resource_types=("security_install_release",),
            organization_id="org-1",
            purposes=("security_install",),
        )

    assert all(policy.name != "Self provision Security Install" for policy in repository.policies())
