"""Operator CLI for external-secret rotation metadata."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from natureai_next.server.postgres_secret_rotation import (
    PostgresSecretRotationRegistry,
)
from natureai_next.server.secret_rotation import SecretRotationRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-secret-rotation")
    parser.add_argument("--backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--postgres-dsn-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--purpose", required=True)
    stage.add_argument("--version-id", required=True)
    stage.add_argument("--provider-reference", required=True)
    stage.add_argument("--created-at-epoch", type=int, required=True)
    activate = commands.add_parser("activate")
    activate.add_argument("--purpose", required=True)
    activate.add_argument("--version-id", required=True)
    activate.add_argument("--activated-at-epoch", type=int, required=True)
    activate.add_argument("--expected-active-version")
    status = commands.add_parser("status")
    status.add_argument("--purpose", required=True)
    return parser


def _repository(args):
    if args.backend == "sqlite":
        if args.database is None:
            raise SystemExit("--database is required with --backend sqlite")
        return SecretRotationRegistry(args.database)
    if args.postgres_dsn_file is None:
        raise SystemExit(
            "--postgres-dsn-file is required with --backend postgresql"
        )
    if (
        not args.postgres_dsn_file.is_file()
        or args.postgres_dsn_file.stat().st_size > 16_384
    ):
        raise SystemExit("PostgreSQL secret-rotation DSN file is invalid")
    dsn = args.postgres_dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL secret-rotation DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "PostgreSQL secret rotation requires the optional "
            "server-postgresql dependency"
        ) from exc
    return PostgresSecretRotationRegistry(
        lambda: psycopg.connect(dsn, connect_timeout=10)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _repository(args)
    if args.command == "stage":
        repository.stage(
            args.purpose,
            args.version_id,
            args.provider_reference,
            args.created_at_epoch,
        )
        print(json.dumps({"staged": True, "version_id": args.version_id}, sort_keys=True))
        return 0
    if args.command == "activate":
        active = repository.activate(
            args.purpose,
            args.version_id,
            args.activated_at_epoch,
            expected_active_version=args.expected_active_version,
        )
        print(json.dumps(asdict(active), sort_keys=True))
        return 0
    active = repository.active(args.purpose)
    versions = repository.versions(args.purpose)
    print(
        json.dumps(
            {
                "active": None if active is None else asdict(active),
                "versions": [asdict(version) for version in versions],
            },
            sort_keys=True,
        )
    )
    return 0
