"""Operator CLI for tenant-scoped, verified security-audit exports."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.audit_export import (
    export_repository_audit,
    verify_tenant_audit_export,
)
from natureai_next.server.postgres_access import PostgresAccessControlRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-audit-export")
    parser.add_argument("--backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--postgres-dsn-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--organization", required=True)
    export.add_argument("--destination", type=Path, required=True)
    export.add_argument("--limit", type=int, default=10_000)
    verify = commands.add_parser("verify")
    verify.add_argument("--source", type=Path, required=True)
    return parser


def _repository(args):
    if args.backend == "sqlite":
        if args.database is None:
            raise SystemExit("--database is required with --backend sqlite")
        if not args.database.is_file():
            raise SystemExit("SQLite access database does not exist")
        return SqliteAccessControlRepository(args.database)
    if args.postgres_dsn_file is None:
        raise SystemExit(
            "--postgres-dsn-file is required with --backend postgresql"
        )
    if (
        not args.postgres_dsn_file.is_file()
        or args.postgres_dsn_file.stat().st_size > 16_384
    ):
        raise SystemExit("PostgreSQL audit DSN file is invalid")
    dsn = args.postgres_dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL audit DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "PostgreSQL audit export requires the optional "
            "server-postgresql dependency"
        ) from exc
    return PostgresAccessControlRepository(
        lambda: psycopg.connect(dsn, connect_timeout=10)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify":
        manifest = verify_tenant_audit_export(args.source)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    repository = _repository(args)
    destination = export_repository_audit(
        repository,
        args.organization,
        args.destination,
        limit=args.limit,
    )
    manifest = verify_tenant_audit_export(destination)
    print(
        json.dumps(
            {"destination": str(destination), "manifest": manifest},
            indent=2,
            sort_keys=True,
        )
    )
    return 0
