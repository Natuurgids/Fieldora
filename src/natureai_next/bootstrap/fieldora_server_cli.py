"""Fieldora server entry point with a one-time, empty-repository admin bootstrap."""

from __future__ import annotations

import getpass
from pathlib import Path
from uuid import uuid4

from natureai_next.application.access_control import AccessAdministrationService
from natureai_next.application.authentication import AuthenticationService
from natureai_next.bootstrap import platform_server_cli, server_cli
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.postgres_access import PostgresAccessControlRepository


def _repository(args):
    if args.access_backend == "postgresql":
        dsn_file = args.postgres_access_dsn_file
        if dsn_file is None or not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
            raise SystemExit("PostgreSQL access DSN file is invalid")
        dsn = dsn_file.read_text(encoding="utf-8").strip()
        if not dsn:
            raise SystemExit("PostgreSQL access DSN file is empty")
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL access control requires the server-postgresql dependency"
            ) from exc
        return PostgresAccessControlRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    paths = resolve_application_paths(args.data_root)
    paths.ensure_directories()
    return SqliteAccessControlRepository(
        paths.subsystem_databases_dir / "access-control.sqlite3"
    )


def _bootstrap_initial_user(arguments: list[str]) -> int:
    args = server_cli.build_parser().parse_args(arguments)
    repository = _repository(args)

    # This boundary is intentionally narrower than normal access administration:
    # it is valid only for a genuinely empty access repository. Once any access
    # state exists, all mutations must go through authenticated PBAC administration.
    if repository.organizations() or repository.identities() or repository.policies():
        raise SystemExit(
            "initial administrator bootstrap requires an empty access repository"
        )

    organization_id = args.organization.strip()
    display_name = args.name.strip()
    username = args.username.strip()
    if not organization_id or not display_name or not username:
        raise SystemExit("organization, name, and username must be non-empty")
    password = args.password or getpass.getpass("Password: ")

    identity = Identity(
        str(uuid4()),
        IdentityKind.USER,
        display_name,
        organization_id,
        attributes={"platform_admin": "true"},
    )
    repository.put_organization(Organization(organization_id, organization_id))
    repository.put_identity(identity)
    repository.assign_role(identity.identity_id, "project-manager", organization_id)

    # Seed exactly one direct policy so the new authenticated actor can perform
    # the remainder of bootstrap through the normal fail-closed administration API.
    repository.put_policy(
        Policy(
            policy_id=str(uuid4()),
            name="Initial bootstrap administrator authority seed",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="",
            subject_id=identity.identity_id,
            role_id="",
            actions=("*",),
            resource_types=("*",),
            organization_id=organization_id,
        )
    )
    repository.put_policy(
        Policy(
            policy_id=str(uuid4()),
            name="Initial project manager read access",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.ROLE,
            source_id="",
            subject_id="",
            role_id="project-manager",
            actions=("view",),
            resource_types=("project", "dossier"),
            organization_id=organization_id,
            purposes=("research",),
        )
    )
    AuthenticationService(repository).set_password(identity.identity_id, username, password)

    platform_server_cli._LAST_REPOSITORY = repository
    platform_server_cli._LAST_IDENTITY = identity
    platform_server_cli._bootstrap_initial_operator(
        lambda repo: AccessAdministrationService(repo, actor_id=identity.identity_id)
    )
    print(f"Created {identity.identity_id}")
    return 0


def main(argv=None) -> int:
    import sys

    arguments = list(sys.argv[1:] if argv is None else argv)
    if platform_server_cli._command(arguments) == "init-user":
        return _bootstrap_initial_user(arguments)
    return platform_server_cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
