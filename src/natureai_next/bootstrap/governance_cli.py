"""Operator CLI for tenant quotas and usage/cost reporting."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.tenant_governance import (
    PostgresTenantGovernance,
    SqliteTenantGovernance,
    costed_usage_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-governance")
    parser.add_argument("--backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--postgres-dsn-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    quota = commands.add_parser("quota-set")
    quota.add_argument("--organization", required=True)
    quota.add_argument("--metric", required=True)
    quota.add_argument("--limit", type=int, required=True)
    quota.add_argument("--period-seconds", type=int, required=True)
    quota.add_argument("--expected-revision", type=int)
    usage = commands.add_parser("usage-report")
    usage.add_argument("--organization", required=True)
    usage.add_argument("--start-epoch", type=int, required=True)
    usage.add_argument("--end-epoch", type=int, required=True)
    usage.add_argument("--unit-costs", type=Path)
    return parser


def _repository(args):
    if args.backend == "sqlite":
        if args.database is None:
            raise SystemExit("--database is required with --backend sqlite")
        return SqliteTenantGovernance(args.database)
    if args.postgres_dsn_file is None:
        raise SystemExit(
            "--postgres-dsn-file is required with --backend postgresql"
        )
    if (
        not args.postgres_dsn_file.is_file()
        or args.postgres_dsn_file.stat().st_size > 16_384
    ):
        raise SystemExit("PostgreSQL governance DSN file is invalid")
    dsn = args.postgres_dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL governance DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "PostgreSQL governance requires the optional server-postgresql dependency"
        ) from exc
    return PostgresTenantGovernance(
        lambda: psycopg.connect(dsn, connect_timeout=10)
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _repository(args)
    if args.command == "quota-set":
        revision = repository.set_quota(
            args.organization,
            args.metric,
            args.limit,
            args.period_seconds,
            expected_revision=args.expected_revision,
        )
        print(
            json.dumps(
                {
                    "organization_id": args.organization,
                    "metric": args.metric,
                    "revision": revision,
                },
                sort_keys=True,
            )
        )
        return 0
    rates = {}
    if args.unit_costs is not None:
        if not args.unit_costs.is_file() or args.unit_costs.stat().st_size > 1_048_576:
            raise SystemExit("unit-cost file is invalid")
        payload = json.loads(args.unit_costs.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in payload.items()
        ):
            raise SystemExit("unit costs must be a JSON object of decimal strings")
        rates = payload
    usage = repository.usage_report(
        args.organization, args.start_epoch, args.end_epoch
    )
    report = costed_usage_report(usage, rates)
    report.update(
        {
            "organization_id": args.organization,
            "start_epoch": args.start_epoch,
            "end_epoch": args.end_epoch,
        }
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0
