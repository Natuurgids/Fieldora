"""Operator CLI for retention records, legal holds, and fenced work."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from natureai_next.server.postgres_retention import PostgresRetentionStore
from natureai_next.server.retention import RetentionCandidate, RetentionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-retention")
    parser.add_argument("--backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--postgres-dsn-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    for argument in ("organization", "resource-type", "resource-id"):
        register.add_argument(f"--{argument}", required=True)
    register.add_argument("--expires-at-epoch", type=int, required=True)
    hold = commands.add_parser("hold-place")
    hold.add_argument("--hold-id", required=True)
    hold.add_argument("--organization", required=True)
    hold.add_argument("--reason", required=True)
    hold.add_argument("--created-at-epoch", type=int, required=True)
    hold.add_argument("--resource-type")
    hold.add_argument("--resource-id")
    release = commands.add_parser("hold-release")
    release.add_argument("--hold-id", required=True)
    release.add_argument("--released-at-epoch", type=int, required=True)
    claim = commands.add_parser("claim")
    claim.add_argument("--worker-id", required=True)
    claim.add_argument("--now-epoch", type=int, required=True)
    claim.add_argument("--lease-seconds", type=int, default=300)
    claim.add_argument("--limit", type=int, default=100)
    complete = commands.add_parser("complete")
    complete.add_argument("--worker-id", required=True)
    complete.add_argument("--organization", required=True)
    complete.add_argument("--resource-type", required=True)
    complete.add_argument("--resource-id", required=True)
    complete.add_argument("--expires-at-epoch", type=int, required=True)
    complete.add_argument("--lease-token", type=int, required=True)
    complete.add_argument("--removed-at-epoch", type=int, required=True)
    return parser


def _repository(args):
    if args.backend == "sqlite":
        if args.database is None:
            raise SystemExit("--database is required with --backend sqlite")
        return RetentionStore(args.database)
    if args.postgres_dsn_file is None:
        raise SystemExit(
            "--postgres-dsn-file is required with --backend postgresql"
        )
    if (
        not args.postgres_dsn_file.is_file()
        or args.postgres_dsn_file.stat().st_size > 16_384
    ):
        raise SystemExit("PostgreSQL retention DSN file is invalid")
    dsn = args.postgres_dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL retention DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "PostgreSQL retention requires the optional server-postgresql dependency"
        ) from exc
    return PostgresRetentionStore(
        lambda: psycopg.connect(dsn, connect_timeout=10)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _repository(args)
    if args.command == "register":
        repository.register(
            args.organization,
            args.resource_type,
            args.resource_id,
            args.expires_at_epoch,
        )
        print(json.dumps({"registered": True}, sort_keys=True))
        return 0
    if args.command == "hold-place":
        repository.place_hold(
            args.hold_id,
            args.organization,
            args.reason,
            args.created_at_epoch,
            resource_type=args.resource_type,
            resource_id=args.resource_id,
        )
        print(json.dumps({"hold_id": args.hold_id, "active": True}, sort_keys=True))
        return 0
    if args.command == "hold-release":
        released = repository.release_hold(args.hold_id, args.released_at_epoch)
        print(json.dumps({"hold_id": args.hold_id, "released": released}, sort_keys=True))
        return 0 if released else 2
    if args.command == "claim":
        rows = repository.claim_due(
            args.worker_id,
            args.now_epoch,
            lease_seconds=args.lease_seconds,
            limit=args.limit,
        )
        print(json.dumps([asdict(row) for row in rows], sort_keys=True))
        return 0
    candidate = RetentionCandidate(
        args.organization,
        args.resource_type,
        args.resource_id,
        args.expires_at_epoch,
        args.lease_token,
    )
    completed = repository.complete_removal(
        candidate, args.worker_id, args.removed_at_epoch
    )
    print(json.dumps({"completed": completed}, sort_keys=True))
    return 0 if completed else 2
