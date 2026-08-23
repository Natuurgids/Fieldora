"""Composition wrapper for the governed Fieldora Platform server.

The established reference server remains the authentication, PBAC, persistence, job,
and transport composition. This wrapper replaces deliberate extension points, adds
long-lived service supervision, and bootstraps explicit privileges for the first
clean-install administrator.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from natureai_next import __version__
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.access_control import PolicyEffect, PolicySource
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.linked_storage_api import LinkedStorageRepository
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.offline_sync import OfflineSyncStore
from natureai_next.server.offline_sync_api import OfflineSyncRepository
from natureai_next.server.operator_control import (
    PostgresOperatorRepository,
    SqliteOperatorRepository,
)
from natureai_next.server.platform_extensions import ProjectOptionalStagedIngestionStore
from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.postgres_offline_sync import PostgresOfflineSyncStore
from natureai_next.server.service_runtime import ServiceRuntimeSupervisor

_LAST_REPOSITORY: Any = None
_LAST_IDENTITY: Any = None


def main(argv: Sequence[str] | None = None) -> int:
    from natureai_next.bootstrap import server_cli

    arguments = list(sys.argv[1:] if argv is None else argv)
    if "register-media" in arguments and "--project" not in arguments:
        arguments.extend(("--project", ""))

    command = _command(arguments)
    supervisor = _runtime_supervisor(arguments, command)
    sync_factory = _offline_sync_factory(arguments, command)
    linked_storage_factory = _linked_storage_factory(arguments, command)
    base_administration = server_cli.AccessAdministrationService
    base_run_one_job = server_cli.run_one_job

    class TrackingAdministration(base_administration):
        def __init__(self, repository: Any) -> None:
            global _LAST_REPOSITORY
            _LAST_REPOSITORY = repository
            super().__init__(repository)

        def create_identity(self, *args: Any, **kwargs: Any):
            global _LAST_IDENTITY
            identity = super().create_identity(*args, **kwargs)
            _LAST_IDENTITY = identity
            return identity

    def guarded_run_one_job(*args: Any, **kwargs: Any):
        if supervisor is not None and not supervisor.state().may_accept_work:
            return None
        return base_run_one_job(*args, **kwargs)

    OfflineFirstFieldoraApi.configure_offline_sync(sync_factory)
    OfflineFirstFieldoraApi.configure_linked_storage(linked_storage_factory)
    server_cli.FieldoraApi = OfflineFirstFieldoraApi
    server_cli.StagedIngestionStore = ProjectOptionalStagedIngestionStore
    server_cli.AccessAdministrationService = TrackingAdministration
    if command == "run-job-worker" and supervisor is not None:
        server_cli.run_one_job = guarded_run_one_job
    try:
        if supervisor is not None:
            supervisor.start()
        result = server_cli.main(arguments)
    finally:
        if supervisor is not None:
            supervisor.stop()
        OfflineFirstFieldoraApi.configure_offline_sync(None)
        OfflineFirstFieldoraApi.configure_linked_storage(None)
        server_cli.FieldoraApi = BrowserFunctionalityFieldoraApi
        server_cli.StagedIngestionStore = ProjectOptionalStagedIngestionStore
        server_cli.AccessAdministrationService = base_administration
        server_cli.run_one_job = base_run_one_job

    if result == 0 and command == "init-user":
        _bootstrap_initial_operator(base_administration)
    return result


def _science_postgres_connect(
    arguments: list[str], *, capability: str
) -> Callable[[], Any]:
    dsn_name = _argument_value(arguments, "--postgres-science-dsn-file")
    if not dsn_name:
        raise SystemExit(
            f"{capability} requires --postgres-science-dsn-file "
            "with --science-backend postgresql"
        )
    dsn_file = Path(dsn_name)
    if not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
        raise SystemExit(f"PostgreSQL Science DSN file is invalid for {capability}")
    dsn = dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit(f"PostgreSQL Science DSN file is empty for {capability}")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            f"PostgreSQL {capability} requires the server-postgresql dependency"
        ) from exc
    return lambda: psycopg.connect(dsn, connect_timeout=10)


def _offline_sync_factory(
    arguments: list[str], command: str
) -> Callable[[], OfflineSyncRepository] | None:
    if command != "serve":
        return None
    science_backend = _argument_value(arguments, "--science-backend") or "sqlite"
    if science_backend == "postgresql":
        connect = _science_postgres_connect(arguments, capability="synchronization")
        return lambda: PostgresOfflineSyncStore(connect)

    root_name = _argument_value(arguments, "--data-root")
    root = None if not root_name else Path(root_name)
    paths = resolve_application_paths(root)
    paths.ensure_directories()
    database_path = paths.subsystem_databases_dir / "offline-sync.sqlite3"
    return lambda: OfflineSyncStore(database_path)


def _linked_storage_factory(
    arguments: list[str], command: str
) -> Callable[[], LinkedStorageRepository] | None:
    if command != "serve":
        return None
    science_backend = _argument_value(arguments, "--science-backend") or "sqlite"
    if science_backend != "postgresql":
        return None
    connect = _science_postgres_connect(arguments, capability="linked storage catalogue")
    return lambda: PostgresLinkedStorageRepository(connect)


def _runtime_supervisor(
    arguments: list[str], command: str
) -> ServiceRuntimeSupervisor | None:
    if command not in {"serve", "run-job-worker"}:
        return None
    service_id = os.environ.get("FIELDORA_SERVICE_ID", "").strip()
    if not service_id:
        raise SystemExit(
            "FIELDORA_SERVICE_ID is required for managed server and worker processes"
        )
    repository = _operator_repository(arguments)
    return ServiceRuntimeSupervisor(
        repository,
        service_id,
        heartbeat_seconds=float(os.environ.get("FIELDORA_HEARTBEAT_SECONDS", "30")),
        software_version=__version__,
        configuration_sha256=os.environ.get("FIELDORA_CONFIGURATION_SHA256", "").strip(),
    )


def _operator_repository(arguments: list[str]):
    governance_backend = _argument_value(arguments, "--governance-backend") or "sqlite"
    if governance_backend == "postgresql":
        dsn_name = _argument_value(arguments, "--postgres-governance-dsn-file")
        if not dsn_name:
            raise SystemExit(
                "service supervision requires --postgres-governance-dsn-file"
            )
        dsn_file = Path(dsn_name)
        if not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
            raise SystemExit("PostgreSQL governance DSN file is invalid")
        dsn = dsn_file.read_text(encoding="utf-8").strip()
        if not dsn:
            raise SystemExit("PostgreSQL governance DSN file is empty")
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "service supervision requires the server-postgresql dependency"
            ) from exc
        return PostgresOperatorRepository(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    root_name = _argument_value(arguments, "--data-root")
    root = None if not root_name else Path(root_name)
    paths = resolve_application_paths(root)
    paths.ensure_directories()
    return SqliteOperatorRepository(
        paths.subsystem_databases_dir / "operator-control.sqlite3"
    )


def _argument_value(arguments: list[str], name: str) -> str:
    try:
        index = arguments.index(name)
    except ValueError:
        return ""
    if index + 1 >= len(arguments):
        return ""
    return arguments[index + 1]


def _command(arguments: list[str]) -> str:
    commands = {
        "serve",
        "init-user",
        "register-media",
        "create-service-key",
        "revoke-service-key",
        "create-device-key",
        "map-oidc-user",
        "verify-audit",
        "rebuild-search",
        "run-jobs-once",
        "run-job-worker",
        "purge-expired-exports",
        "create-project-contract",
        "set-contract-status",
        "init-export-signing-key",
        "verify-project-export",
        "generate-export-recipient-key",
        "decrypt-project-export",
    }
    return next((item for item in arguments if item in commands), "")


def _bootstrap_initial_operator(administration_type: Any) -> None:
    global _LAST_IDENTITY
    if _LAST_REPOSITORY is None or _LAST_IDENTITY is None:
        raise RuntimeError("initial administrator bootstrap identity was not captured")
    identity = replace(
        _LAST_IDENTITY,
        attributes={**_LAST_IDENTITY.attributes, "platform_admin": "true"},
    )
    _LAST_REPOSITORY.put_identity(identity)
    _LAST_IDENTITY = identity
    administration = administration_type(_LAST_REPOSITORY)
    organization_id = identity.organization_id
    administration.grant_role(identity.identity_id, "platform-operator", organization_id)
    administration.create_policy(
        name="Initial governed evidence and scientific collaboration",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="project-manager",
        actions=(
            "view",
            "download",
            "upload",
            "edit",
            "search",
            "submit_evidence",
            "view_submission",
            "request_review",
            "view_review",
            "determine",
            "accept_determination",
            "link",
            "unlink",
        ),
        resource_types=(
            "asset",
            "collection",
            "submission",
            "review_case",
            "media_association",
        ),
        organization_id=organization_id,
        purposes=("research",),
    )
    administration.create_policy(
        name="Initial project portfolio creator",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="platform-operator",
        actions=("create", "view", "edit"),
        resource_types=("project",),
        organization_id=organization_id,
        purposes=("research",),
    )
    administration.create_policy(
        name="Initial governed data-contract administrator",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="platform-operator",
        actions=("administer_contracts", "approve_contracts"),
        resource_types=("contract",),
        organization_id=organization_id,
        purposes=("administration",),
    )
    administration.create_policy(
        name="Initial facilities planning and relocation access",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="project-manager",
        actions=("view", "create", "edit", "update"),
        resource_types=(
            "operations.drawing",
            "operations.layout",
            "operations.relocation",
        ),
        organization_id=organization_id,
        purposes=("operations",),
    )
    administration.create_policy(
        name="Initial Fieldora infrastructure operator",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="platform-operator",
        actions=(
            "infrastructure.view",
            "service.enroll",
            "service.heartbeat",
            "service.activate",
            "service.drain",
            "service.stop",
            "service.revoke",
            "bulk_ingest.create",
            "bulk_ingest.view",
            "logs.view",
            "capacity.view",
        ),
        resource_types=("infrastructure", "bulk_ingest"),
        organization_id=organization_id,
        purposes=("administration",),
    )


if __name__ == "__main__":
    raise SystemExit(main())
