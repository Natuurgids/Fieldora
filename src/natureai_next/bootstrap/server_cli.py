"""Command line for the one-node Fieldora reference server."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.application.authentication import AuthenticationService
from natureai_next.application.device_authorization import DeviceAuthorizationService
from natureai_next.application.oidc import OidcAuthenticationService, OidcConfiguration
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.access_control import IdentityKind, PolicyEffect, PolicySource
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.api import FieldoraApi, ScienceReadProjection
from natureai_next.server.export_encryption import (
    decrypt_project_export,
    generate_recipient_identity,
)
from natureai_next.server.export_signing import (
    ExportSigningIdentity,
    verify_export_attestation,
)
from natureai_next.server.exports import GovernedExportStore
from natureai_next.server.http import serve
from natureai_next.server.jobs import ServerJobStore, run_one_job
from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.object_storage import S3ObjectStore
from natureai_next.server.postgres_access import PostgresAccessControlRepository
from natureai_next.server.postgres_exports import PostgresExportMetadataRepository
from natureai_next.server.postgres_jobs import PostgresServerJobStore
from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_science import PostgresScienceRepository
from natureai_next.server.readiness import ReadinessMonitor
from natureai_next.server.search import OpenSearchProjection, ServerSearchProjection
from natureai_next.server.staged_ingestion import (
    ClamAvScanner,
    StagedIngestionService,
    StagedIngestionStore,
)
from natureai_next.server.tenant_governance import (
    PostgresTenantGovernance,
    SqliteTenantGovernance,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-server")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--media-object-store", choices=("filesystem", "s3"), default="filesystem"
    )
    parser.add_argument("--s3-bucket")
    parser.add_argument("--s3-prefix", default="fieldora/media")
    parser.add_argument("--s3-export-prefix", default="fieldora/exports")
    parser.add_argument("--s3-endpoint-url")
    parser.add_argument("--s3-region")
    parser.add_argument(
        "--search-backend", choices=("sqlite", "opensearch"), default="sqlite"
    )
    parser.add_argument("--opensearch-endpoint")
    parser.add_argument("--opensearch-index", default="fieldora-search")
    parser.add_argument("--opensearch-timeout", type=float, default=10.0)
    parser.add_argument("--opensearch-bearer-token-file", type=Path)
    parser.add_argument(
        "--job-backend", choices=("sqlite", "postgresql"), default="sqlite"
    )
    parser.add_argument("--postgres-jobs-dsn-file", type=Path)
    parser.add_argument(
        "--media-metadata-backend",
        choices=("sqlite", "postgresql"),
        default="sqlite",
    )
    parser.add_argument("--postgres-media-dsn-file", type=Path)
    parser.add_argument(
        "--export-metadata-backend",
        choices=("sqlite", "postgresql"),
        default="sqlite",
    )
    parser.add_argument("--postgres-exports-dsn-file", type=Path)
    parser.add_argument(
        "--science-backend", choices=("sqlite", "postgresql"), default="sqlite"
    )
    parser.add_argument("--postgres-science-dsn-file", type=Path)
    parser.add_argument(
        "--access-backend", choices=("sqlite", "postgresql"), default="sqlite"
    )
    parser.add_argument("--postgres-access-dsn-file", type=Path)
    parser.add_argument(
        "--governance-backend", choices=("sqlite", "postgresql"), default="sqlite"
    )
    parser.add_argument("--postgres-governance-dsn-file", type=Path)
    parser.add_argument("--clamav-executable", default="clamscan")
    parser.add_argument("--staged-import-batch-size", type=int, default=250)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--oidc-issuer")
    run.add_argument("--oidc-audience")
    run.add_argument("--oidc-jwks", type=Path)
    run.add_argument("--oidc-discovery", action="store_true")
    run.add_argument("--oidc-refresh-seconds", type=int, default=3600)
    run.add_argument("--tls-certificate", type=Path)
    run.add_argument("--tls-private-key", type=Path)
    run.add_argument("--allow-insecure-http", action="store_true")
    run.add_argument("--drain-seconds", type=float, default=10)
    initialize = commands.add_parser("init-user")
    initialize.add_argument("--organization", required=True)
    initialize.add_argument("--name", required=True)
    initialize.add_argument("--username", required=True)
    initialize.add_argument("--password")
    register = commands.add_parser("register-media")
    register.add_argument("--source", type=Path, required=True)
    register.add_argument("--organization", required=True)
    register.add_argument("--project", required=True)
    service = commands.add_parser("create-service-key")
    service.add_argument("--organization", required=True)
    service.add_argument("--name", required=True)
    service.add_argument("--role", required=True)
    service.add_argument("--label", default="integration")
    service.add_argument("--days", type=int, default=90)
    revoke = commands.add_parser("revoke-service-key")
    revoke.add_argument("--credential-id", required=True)
    device = commands.add_parser("create-device-key")
    device.add_argument("--organization", required=True)
    device.add_argument("--project", required=True)
    device.add_argument("--name", required=True)
    device.add_argument("--role", default="field-device")
    device.add_argument("--days", type=int, default=30)
    mapping = commands.add_parser("map-oidc-user")
    mapping.add_argument("--identity-id", required=True)
    mapping.add_argument("--issuer", required=True)
    mapping.add_argument("--subject", required=True)
    commands.add_parser("verify-audit")
    rebuild = commands.add_parser("rebuild-search")
    rebuild.add_argument("--organization", required=True)
    commands.add_parser("run-jobs-once")
    worker = commands.add_parser("run-job-worker")
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--max-jobs", type=int, default=100)
    worker.add_argument("--lease-seconds", type=int, default=300)
    worker.add_argument("--continuous", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=2.0)
    commands.add_parser("purge-expired-exports")
    contract = commands.add_parser("create-project-contract")
    contract.add_argument("--title", required=True)
    contract.add_argument("--organization", required=True)
    contract.add_argument("--project", required=True)
    contract.add_argument("--subject-id", required=True)
    contract.add_argument("--starts-at", required=True)
    contract.add_argument("--ends-at", required=True)
    contract.add_argument(
        "--rights", required=True,
        help="Comma-separated: view,search,export,view_job,download_export,upload",
    )
    contract_status = commands.add_parser("set-contract-status")
    contract_status.add_argument("--contract-id", required=True)
    contract_status.add_argument(
        "--status", required=True, choices=("active", "suspended", "terminated")
    )
    signing = commands.add_parser("init-export-signing-key")
    signing.add_argument("--key-id", default="fieldora-export-v1")
    verify_export = commands.add_parser("verify-project-export")
    verify_export.add_argument("--source", type=Path, required=True)
    verify_export.add_argument("--attestation", type=Path, required=True)
    verify_export.add_argument("--trusted-keys", type=Path, required=True)
    recipient = commands.add_parser("generate-export-recipient-key")
    recipient.add_argument("--key-id", required=True)
    recipient.add_argument("--output-dir", type=Path, required=True)
    decrypt_export = commands.add_parser("decrypt-project-export")
    decrypt_export.add_argument("--source", type=Path, required=True)
    decrypt_export.add_argument("--destination", type=Path, required=True)
    decrypt_export.add_argument("--private-key", type=Path, required=True)
    return parser


def validate_listener_security(
    host: str,
    certificate: Path | None,
    private_key: Path | None,
    *,
    allow_insecure_http: bool = False,
) -> bool:
    tls_values = (certificate, private_key)
    if any(tls_values) and not all(tls_values):
        raise ValueError("TLS certificate and private key must be configured together")
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback and not all(tls_values) and not allow_insecure_http:
        raise ValueError(
            "non-loopback listeners require TLS; allow insecure HTTP only behind "
            "a trusted TLS terminator"
        )
    return bool(all(tls_values))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    readiness_postgres_dsns: set[str] = set()
    paths = resolve_application_paths(args.data_root)
    paths.ensure_directories()
    if args.access_backend == "postgresql":
        if args.postgres_access_dsn_file is None:
            raise SystemExit(
                "--postgres-access-dsn-file is required with "
                "--access-backend postgresql"
            )
        if (
            not args.postgres_access_dsn_file.is_file()
            or args.postgres_access_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL access DSN file is invalid")
        access_dsn = args.postgres_access_dsn_file.read_text(
            encoding="utf-8"
        ).strip()
        if not access_dsn:
            raise SystemExit("PostgreSQL access DSN file is empty")
        readiness_postgres_dsns.add(access_dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL access control requires the optional "
                "server-postgresql dependency"
            ) from exc
        repository = PostgresAccessControlRepository(
            lambda: psycopg.connect(access_dsn, connect_timeout=10)
        )
    else:
        repository = SqliteAccessControlRepository(
            paths.subsystem_databases_dir / "access-control.sqlite3"
        )
    authentication = AuthenticationService(repository)
    device_authorization = DeviceAuthorizationService(repository, authentication)
    science_path = paths.subsystem_databases_dir / "science.sqlite3"
    if args.science_backend == "postgresql":
        if args.postgres_science_dsn_file is None:
            raise SystemExit(
                "--postgres-science-dsn-file is required with "
                "--science-backend postgresql"
            )
        if (
            not args.postgres_science_dsn_file.is_file()
            or args.postgres_science_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL Science DSN file is invalid")
        science_dsn = args.postgres_science_dsn_file.read_text(
            encoding="utf-8"
        ).strip()
        if not science_dsn:
            raise SystemExit("PostgreSQL Science DSN file is empty")
        readiness_postgres_dsns.add(science_dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL Science requires the optional "
                "server-postgresql dependency"
            ) from exc
        science = PostgresScienceRepository(
            lambda: psycopg.connect(science_dsn, connect_timeout=10)
        )
        science_source = science
    else:
        science = ScienceReadProjection(science_path)
        science_source = science_path
    object_store = None
    export_object_store = None
    if args.media_object_store == "s3":
        if not args.s3_bucket:
            raise SystemExit("--s3-bucket is required for S3 media storage")
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit(
                "S3 media storage requires the optional server-s3 dependency"
            ) from exc
        client_options = {}
        if args.s3_endpoint_url:
            client_options["endpoint_url"] = args.s3_endpoint_url
        if args.s3_region:
            client_options["region_name"] = args.s3_region
        object_store = S3ObjectStore(
            boto3.client("s3", **client_options), args.s3_bucket, args.s3_prefix
        )
        export_object_store = S3ObjectStore(
            boto3.client("s3", **client_options),
            args.s3_bucket,
            args.s3_export_prefix,
        )
    media_metadata = None
    if args.media_metadata_backend == "postgresql":
        if args.postgres_media_dsn_file is None:
            raise SystemExit(
                "--postgres-media-dsn-file is required with "
                "--media-metadata-backend postgresql"
            )
        if (
            not args.postgres_media_dsn_file.is_file()
            or args.postgres_media_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL media DSN file is invalid")
        media_dsn = args.postgres_media_dsn_file.read_text(
            encoding="utf-8"
        ).strip()
        if not media_dsn:
            raise SystemExit("PostgreSQL media DSN file is empty")
        readiness_postgres_dsns.add(media_dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL media metadata requires the optional "
                "server-postgresql dependency"
            ) from exc
        media_metadata = PostgresMediaMetadataRepository(
            lambda: psycopg.connect(media_dsn, connect_timeout=10)
        )
    media = GovernedMediaStore(
        paths.subsystem_databases_dir / "server-media.sqlite3",
        paths.local_root / "server-media",
        object_store=object_store,
        metadata=media_metadata,
    )
    if args.search_backend == "opensearch":
        if not args.opensearch_endpoint:
            raise SystemExit(
                "--opensearch-endpoint is required with --search-backend opensearch"
            )
        try:
            bearer_token = ""
            if args.opensearch_bearer_token_file is not None:
                if (
                    not args.opensearch_bearer_token_file.is_file()
                    or args.opensearch_bearer_token_file.stat().st_size > 16_384
                ):
                    raise ValueError("OpenSearch bearer-token file is invalid")
                bearer_token = args.opensearch_bearer_token_file.read_text(
                    encoding="utf-8"
                ).strip()
                if not bearer_token:
                    raise ValueError("OpenSearch bearer-token file is empty")
            search = OpenSearchProjection(
                args.opensearch_endpoint,
                args.opensearch_index,
                args.opensearch_timeout,
                bearer_token=bearer_token,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        search = ServerSearchProjection(
            paths.subsystem_databases_dir / "server-search.sqlite3"
        )
    if args.job_backend == "postgresql":
        if args.postgres_jobs_dsn_file is None:
            raise SystemExit(
                "--postgres-jobs-dsn-file is required with "
                "--job-backend postgresql"
            )
        if (
            not args.postgres_jobs_dsn_file.is_file()
            or args.postgres_jobs_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL jobs DSN file is invalid")
        dsn = args.postgres_jobs_dsn_file.read_text(encoding="utf-8").strip()
        if not dsn:
            raise SystemExit("PostgreSQL jobs DSN file is empty")
        readiness_postgres_dsns.add(dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL jobs require the optional server-postgresql dependency"
            ) from exc
        jobs = PostgresServerJobStore(
            lambda: psycopg.connect(dsn, connect_timeout=10)
        )
    else:
        jobs = ServerJobStore(paths.subsystem_databases_dir / "server-jobs.sqlite3")
    staged_ingestion = StagedIngestionService(
        StagedIngestionStore(
            paths.subsystem_databases_dir / "staged-ingestion.sqlite3",
            paths.local_root / "quarantine",
        ),
        jobs,
        malware_scanner=ClamAvScanner(args.clamav_executable),
        import_batch_size=args.staged_import_batch_size,
    )
    export_metadata = None
    if args.export_metadata_backend == "postgresql":
        if args.postgres_exports_dsn_file is None:
            raise SystemExit(
                "--postgres-exports-dsn-file is required with "
                "--export-metadata-backend postgresql"
            )
        if (
            not args.postgres_exports_dsn_file.is_file()
            or args.postgres_exports_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL exports DSN file is invalid")
        exports_dsn = args.postgres_exports_dsn_file.read_text(
            encoding="utf-8"
        ).strip()
        if not exports_dsn:
            raise SystemExit("PostgreSQL exports DSN file is empty")
        readiness_postgres_dsns.add(exports_dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL export metadata requires the optional "
                "server-postgresql dependency"
            ) from exc
        export_metadata = PostgresExportMetadataRepository(
            lambda: psycopg.connect(exports_dsn, connect_timeout=10)
        )
    exports = GovernedExportStore(
        paths.subsystem_databases_dir / "server-exports.sqlite3",
        paths.local_root / "server-exports",
        metadata=export_metadata,
        object_store=export_object_store,
    )
    signing_root = paths.local_root / "server-signing"
    signing_key = signing_root / "export-private.pem"
    signing_trust = signing_root / "export-trusted-keys.json"
    if args.command == "init-user":
        password = args.password or getpass.getpass("Password: ")
        administration = AccessAdministrationService(repository)
        if not any(
            item.organization_id == args.organization
            for item in repository.organizations()
        ):
            administration.create_organization(args.organization, args.organization)
        identity = administration.create_identity(
            args.name, args.organization, IdentityKind.USER
        )
        authentication.set_password(identity.identity_id, args.username, password)
        administration.grant_role(
            identity.identity_id, "project-manager", args.organization
        )
        administration.create_policy(
            name="Initial project manager read access",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.ROLE,
            role_id="project-manager",
            actions=("view",),
            resource_types=("project", "dossier"),
            organization_id=args.organization,
            purposes=("research",),
        )
        print(f"Created {identity.identity_id}")
        return 0
    if args.command == "register-media":
        record = media.register(args.source, args.organization, args.project)
        print(record.media_id)
        return 0
    if args.command == "create-service-key":
        administration = AccessAdministrationService(repository)
        if not any(
            item.organization_id == args.organization
            for item in repository.organizations()
        ):
            administration.create_organization(args.organization, args.organization)
        identity = administration.create_identity(
            args.name, args.organization, IdentityKind.SERVICE
        )
        administration.grant_role(
            identity.identity_id, args.role, args.organization
        )
        credential_id, token = authentication.issue_service_key(
            identity.identity_id, args.label, timedelta(days=max(1, args.days))
        )
        print(f"Credential ID: {credential_id}")
        print(f"API key (shown once): {token}")
        return 0
    if args.command == "create-device-key":
        administration = AccessAdministrationService(repository)
        if not any(
            item.organization_id == args.organization
            for item in repository.organizations()
        ):
            administration.create_organization(args.organization, args.organization)
        identity = administration.create_identity(
            args.name, args.organization, IdentityKind.DEVICE
        )
        administration.grant_role(
            identity.identity_id, args.role, args.organization, args.project
        )
        credential_id, token = authentication.issue_machine_key(
            identity.identity_id, f"device:{args.project}",
            timedelta(days=max(1, args.days)),
        )
        print(f"Device ID: {identity.identity_id}")
        print(f"Credential ID: {credential_id}")
        print(f"Device key (shown once): {token}")
        return 0
    if args.command == "revoke-service-key":
        authentication.revoke_service_key(args.credential_id)
        print("Credential revoked")
        return 0
    if args.command == "map-oidc-user":
        identity = repository.identity(args.identity_id)
        if identity is None or identity.kind is not IdentityKind.USER:
            raise SystemExit("An existing user identity is required")
        repository.map_federated_identity(
            args.issuer, args.subject, args.identity_id
        )
        print("Federated identity mapped")
        return 0
    if args.command == "verify-audit":
        verified, detail = repository.verify_audit_chain()
        print(detail)
        return 0 if verified else 2
    if args.command == "rebuild-search":
        count = search.rebuild(
            science_source, args.organization
        )
        print(f"Indexed {count} records")
        return 0
    if args.command in {"run-jobs-once", "run-job-worker"}:
        signer = None
        if signing_key.is_file() and signing_trust.is_file():
            trusted = json.loads(signing_trust.read_text(encoding="utf-8"))
            key_ids = tuple(trusted.get("keys", {}))
            if len(key_ids) != 1:
                raise SystemExit("Export trust file must contain exactly one signing key")
            signer = ExportSigningIdentity.load(key_ids[0], signing_key)
        if args.command == "run-jobs-once":
            job = run_one_job(
                jobs, search, science_source,
                exports, signer, staged_ingestion=staged_ingestion,
            )
            print("No queued job" if job is None else f"{job.job_id}: {job.status}")
            return 0 if job is None or job.status == "succeeded" else 2
        if not 1 <= args.max_jobs <= 10_000:
            raise SystemExit("--max-jobs must be between 1 and 10000")
        if not 30 <= args.lease_seconds <= 86_400:
            raise SystemExit("--lease-seconds must be between 30 and 86400")
        if not 0.1 <= args.poll_seconds <= 60:
            raise SystemExit("--poll-seconds must be between 0.1 and 60")
        processed = 0
        failures = 0
        shutdown = ShutdownCoordinator()
        with shutdown.installed():
            while processed < args.max_jobs and not shutdown.requested:
                job = run_one_job(
                    jobs, search, science_source,
                    exports, signer, args.worker_id, args.lease_seconds,
                    staged_ingestion,
                )
                if job is None:
                    if not args.continuous:
                        break
                    shutdown.wait(args.poll_seconds)
                    continue
                processed += 1
                failures += int(job.status != "succeeded")
                print(f"{job.job_id}: {job.status}")
        print(f"Worker {args.worker_id}: processed {processed}, failed {failures}")
        return 0 if failures == 0 else 2
    if args.command == "purge-expired-exports":
        count = exports.purge_expired()
        print(f"Purged {count} export payload(s)")
        return 0
    if args.command == "create-project-contract":
        contract, policies = AccessAdministrationService(
            repository
        ).create_project_contract_grant(
            title=args.title,
            organization_id=args.organization,
            project_id=args.project,
            subject_id=args.subject_id,
            starts_at_utc=args.starts_at,
            ends_at_utc=args.ends_at,
            rights=tuple(item.strip() for item in args.rights.split(",")),
        )
        print(f"Contract ID: {contract.contract_id}")
        print(f"Policies: {len(policies)}")
        return 0
    if args.command == "set-contract-status":
        contract = AccessAdministrationService(repository).set_contract_status(
            args.contract_id, args.status
        )
        print(f"{contract.contract_id}: {contract.status}")
        return 0
    if args.command == "init-export-signing-key":
        identity = ExportSigningIdentity.generate(
            args.key_id, signing_key, signing_trust
        )
        print(f"Signing key ID: {identity.key_id}")
        print(f"Trusted public keys: {signing_trust}")
        return 0
    if args.command == "verify-project-export":
        attestation = json.loads(args.attestation.read_text(encoding="utf-8"))
        digest = verify_export_attestation(
            args.source, attestation, args.trusted_keys
        )
        print(f"Verified SHA-256: {digest}")
        return 0
    if args.command == "generate-export-recipient-key":
        private_path = args.output_dir / f"{args.key_id}-private.pem"
        public_path = args.output_dir / f"{args.key_id}-public.json"
        generate_recipient_identity(args.key_id, private_path, public_path)
        print(f"Recipient key ID: {args.key_id}")
        print(f"Public key: {public_path}")
        return 0
    if args.command == "decrypt-project-export":
        key_id = decrypt_project_export(
            args.source, args.destination, args.private_key
        )
        print(f"Decrypted for recipient key: {key_id}")
        return 0
    web_root = Path(__file__).parent.parent / "resources" / "server_web"
    if bool(args.oidc_issuer) != bool(args.oidc_audience):
        raise SystemExit("OIDC issuer and audience must be configured together")
    if args.oidc_discovery and args.oidc_jwks:
        raise SystemExit("OIDC discovery and a local JWKS are mutually exclusive")
    if args.oidc_issuer and not (args.oidc_discovery or args.oidc_jwks):
        raise SystemExit("OIDC requires discovery or a local JWKS")
    oidc_enabled = bool(args.oidc_issuer)
    oidc = (
        OidcAuthenticationService(
            OidcConfiguration(
                args.oidc_issuer,
                args.oidc_audience,
                args.oidc_jwks,
                discovery=args.oidc_discovery,
                refresh_seconds=args.oidc_refresh_seconds,
            ),
            repository,
        )
        if oidc_enabled else None
    )
    if args.governance_backend == "postgresql":
        if args.postgres_governance_dsn_file is None:
            raise SystemExit(
                "--postgres-governance-dsn-file is required with "
                "--governance-backend postgresql"
            )
        if (
            not args.postgres_governance_dsn_file.is_file()
            or args.postgres_governance_dsn_file.stat().st_size > 16_384
        ):
            raise SystemExit("PostgreSQL governance DSN file is invalid")
        governance_dsn = args.postgres_governance_dsn_file.read_text(
            encoding="utf-8"
        ).strip()
        if not governance_dsn:
            raise SystemExit("PostgreSQL governance DSN file is empty")
        readiness_postgres_dsns.add(governance_dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL governance requires the optional "
                "server-postgresql dependency"
            ) from exc
        governance = PostgresTenantGovernance(
            lambda: psycopg.connect(governance_dsn, connect_timeout=10)
        )
    else:
        governance = SqliteTenantGovernance(
            paths.subsystem_databases_dir / "tenant-governance.sqlite3"
        )
    readiness_checks = {}
    if readiness_postgres_dsns:
        try:
            import psycopg
        except ImportError as exc:
            raise SystemExit(
                "PostgreSQL readiness requires the optional "
                "server-postgresql dependency"
            ) from exc

        def postgres_ready(dsn: str) -> bool:
            with psycopg.connect(dsn, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return cursor.fetchone() == (1,)

        for index, readiness_dsn in enumerate(sorted(readiness_postgres_dsns), 1):
            readiness_checks[f"postgres-{index}"] = (
                lambda value=readiness_dsn: postgres_ready(value)
            )
    if object_store is not None:
        readiness_checks["object-storage"] = object_store.ready
    if isinstance(search, OpenSearchProjection):
        readiness_checks["search"] = search.ready
    readiness = (
        ReadinessMonitor(readiness_checks, cache_seconds=2)
        if readiness_checks else None
    )
    application = FieldoraApi(
        authentication,
        PolicyDecisionService(repository),
        science,
        web_root,
        media,
        device_authorization,
        oidc,
        repository,
        search,
        jobs,
        exports,
        governance,
        readiness,
        staged_ingestion,
        runtime_profile={
            "access": args.access_backend,
            "science": args.science_backend,
            "media_metadata": args.media_metadata_backend,
            "jobs": args.job_backend,
            "export_metadata": args.export_metadata_backend,
            "governance": args.governance_backend,
            "search": args.search_backend,
            "object_storage": args.media_object_store,
        },
    )
    try:
        tls_enabled = validate_listener_security(
            args.host, args.tls_certificate, args.tls_private_key,
            allow_insecure_http=args.allow_insecure_http,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not 0 <= args.drain_seconds <= 300:
        raise SystemExit("--drain-seconds must be between 0 and 300")
    scheme = "https" if tls_enabled else "http"
    print(f"Fieldora server listening on {scheme}://{args.host}:{args.port}")
    serve(
        application, args.host, args.port,
        certificate=args.tls_certificate, private_key=args.tls_private_key,
        on_shutdown=None if readiness is None else readiness.begin_draining,
        shutdown_grace_seconds=args.drain_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
