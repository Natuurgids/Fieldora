"""One-time bootstrap of the first Fieldora PBAC administrator.

This helper is intentionally narrower than normal access administration: it only
runs against an empty access-control repository. Once any identity,
organization, or policy exists, normal authenticated PBAC administration must
be used instead.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

import psycopg

from natureai_next.application.authentication import AuthenticationService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.postgres_access import PostgresAccessControlRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn-file", type=Path, required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    dsn = args.dsn_file.read_text(encoding="utf-8").strip()
    repository = PostgresAccessControlRepository(
        lambda: psycopg.connect(dsn, connect_timeout=10)
    )
    if repository.organizations() or repository.identities() or repository.policies():
        raise SystemExit(
            "initial administrator bootstrap requires an empty access-control repository"
        )

    organization_id = args.organization.strip()
    if not organization_id:
        raise SystemExit("organization is required")
    identity = Identity(
        str(uuid4()),
        IdentityKind.USER,
        args.name.strip(),
        organization_id,
        attributes={"platform_admin": "true"},
    )
    repository.put_organization(Organization(organization_id, organization_id))
    repository.put_identity(identity)
    AuthenticationService(repository).set_password(
        identity.identity_id, args.username, args.password
    )
    repository.assign_role(identity.identity_id, "project-manager", organization_id)
    repository.put_policy(
        Policy(
            policy_id=str(uuid4()),
            name="Initial platform administrator access",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="initial-bootstrap",
            subject_id=identity.identity_id,
            role_id="",
            actions=("administer",),
            resource_types=("*",),
            organization_id=organization_id,
            purposes=("access_control_administration",),
            priority=1000,
        )
    )
    repository.put_policy(
        Policy(
            policy_id=str(uuid4()),
            name="Initial project manager read access",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.ROLE,
            source_id="initial-bootstrap",
            subject_id="",
            role_id="project-manager",
            actions=("view",),
            resource_types=("project", "dossier"),
            organization_id=organization_id,
            purposes=("research",),
        )
    )
    print(f"Created {identity.identity_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
