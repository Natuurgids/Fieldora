from pathlib import Path

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.domain.access_control import (
    AccessRequest,
    IdentityKind,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


def test_pbac_defaults_to_deny_and_enforces_scope_and_fields(tmp_path: Path) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    user = administration.create_identity("Researcher", "org-a", IdentityKind.USER)
    administration.grant_role(user.identity_id, "researcher", "org-a", "project-1")
    administration.create_policy(
        name="Scoped research viewer",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="researcher",
        actions=("view",),
        resource_types=("dossier",),
        organization_id="org-a",
        project_id="project-1",
        purposes=("research",),
        fields=("title", "notes"),
    )
    decide = PolicyDecisionService(repository).decide
    assert decide(
        AccessRequest(
            user.identity_id, "view", "dossier", "d1", "org-a", "project-1",
            "research", ("title",),
        )
    ).allowed
    assert not decide(
        AccessRequest(user.identity_id, "download", "dossier", "d1", "org-a", "project-1")
    ).allowed
    assert not decide(
        AccessRequest(user.identity_id, "view", "dossier", "d1", "org-b", "project-1")
    ).allowed
    assert not decide(
        AccessRequest(
            user.identity_id, "view", "dossier", "d1", "org-a", "project-1",
            "research", ("sensitive_location",),
        )
    ).allowed


def test_contract_expiry_and_explicit_object_deny_override_allow(
    tmp_path: Path,
) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    user = administration.create_identity("Guest", "org-a", IdentityKind.USER)
    contract = administration.create_contract(
        "Research access", "org-a",
        "2026-01-01T00:00:00+00:00", "2026-12-31T00:00:00+00:00",
    )
    administration.create_policy(
        name="Contract view",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.CONTRACT,
        source_id=contract.contract_id,
        subject_id=user.identity_id,
        actions=("view",),
        resource_types=("asset",),
        organization_id="org-a",
    )
    administration.create_policy(
        name="Restricted specimen",
        effect=PolicyEffect.DENY,
        source=PolicySource.OBJECT_GRANT,
        subject_id=user.identity_id,
        actions=("view",),
        resource_types=("asset",),
        resource_id="restricted",
        organization_id="org-a",
    )
    decide = PolicyDecisionService(repository).decide
    assert decide(
        AccessRequest(
            user.identity_id, "view", "asset", "ordinary", "org-a",
            requested_at_utc="2026-06-01T00:00:00+00:00",
        )
    ).allowed
    assert not decide(
        AccessRequest(
            user.identity_id, "view", "asset", "restricted", "org-a",
            requested_at_utc="2026-06-01T00:00:00+00:00",
        )
    ).allowed
    assert not decide(
        AccessRequest(
            user.identity_id, "view", "asset", "ordinary", "org-a",
            requested_at_utc="2027-01-01T00:00:00+00:00",
        )
    ).allowed
    assert len(repository.audit_events()) == 3


def test_group_roles_and_organizations_are_managed(tmp_path: Path) -> None:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    administration = AccessAdministrationService(repository)
    organization = administration.create_organization("org-a", "Field Research")
    group = administration.create_identity("Reviewers", "org-a", IdentityKind.GROUP)
    user = administration.create_identity("Reviewer", "org-a", IdentityKind.USER)
    administration.add_group_member(group.identity_id, user.identity_id)
    administration.grant_role(group.identity_id, "reviewer", "org-a")
    administration.create_policy(
        name="Group review",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="reviewer",
        actions=("review",),
        resource_types=("dossier",),
        organization_id="org-a",
    )
    assert repository.organizations() == (organization,)
    assert group.identity_id in repository.group_ids(user.identity_id)
    assert PolicyDecisionService(repository).decide(
        AccessRequest(user.identity_id, "review", "dossier", "d1", "org-a")
    ).allowed
