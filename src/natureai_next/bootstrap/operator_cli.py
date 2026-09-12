"""Operator CLI for explicit Fieldora service enrollment and lifecycle."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.operator_control import (
    PostgresOperatorRepository,
    ServiceState,
    SqliteOperatorRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-operator")
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--postgres-dsn-file", type=Path)
    backend.add_argument("--sqlite-database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    enroll = commands.add_parser("enroll")
    enroll.add_argument("--organization", required=True)
    enroll.add_argument("--service-id", required=True)
    enroll.add_argument("--name", required=True)
    enroll.add_argument("--type", dest="service_type", required=True)
    enroll.add_argument("--node", required=True)
    enroll.add_argument("--software-version", default="")
    enroll.add_argument("--configuration-sha256", default="")
    enroll.add_argument("--certificate-serial", required=True)
    enroll.add_argument("--certificate-not-after-epoch", type=int, required=True)
    list_services = commands.add_parser("list")
    list_services.add_argument("--organization", required=True)
    for name in ("activate", "drain", "stop", "revoke"):
        command = commands.add_parser(name)
        command.add_argument("--service-id", required=True)
    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("--service-id", required=True)
    heartbeat.add_argument("--software-version", default="")
    heartbeat.add_argument("--configuration-sha256", default="")
    heartbeat.add_argument("--certificate-serial", default="")
    heartbeat.add_argument("--certificate-not-after-epoch", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = _repository(args)
    if args.command == "enroll":
        record = repository.enroll(
            organization_id=args.organization,
            service_id=args.service_id,
            name=args.name,
            service_type=args.service_type,
            node_name=args.node,
            software_version=args.software_version,
            configuration_sha256=args.configuration_sha256,
            certificate_serial=args.certificate_serial,
            certificate_not_after_epoch=args.certificate_not_after_epoch,
        )
        print(json.dumps(record.as_dict(), sort_keys=True))
        return 0
    if args.command == "list":
        print(
            json.dumps(
                [item.as_dict() for item in repository.services(args.organization)],
                sort_keys=True,
            )
        )
        return 0
    if args.command == "heartbeat":
        record = repository.heartbeat(
            args.service_id,
            software_version=args.software_version,
            configuration_sha256=args.configuration_sha256,
            certificate_serial=args.certificate_serial,
            certificate_not_after_epoch=args.certificate_not_after_epoch,
        )
        print(json.dumps(record.as_dict(), sort_keys=True))
        return 0
    state = ServiceState(args.command if args.command != "activate" else "active")
    record = repository.transition(args.service_id, state)
    print(json.dumps(record.as_dict(), sort_keys=True))
    return 0


def _repository(args):
    if args.sqlite_database is not None:
        return SqliteOperatorRepository(args.sqlite_database)
    dsn_file = args.postgres_dsn_file
    if dsn_file is None or not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
        raise SystemExit("PostgreSQL operator DSN file is invalid")
    dsn = dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise SystemExit("PostgreSQL operator DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("PostgreSQL operator registry requires server-postgresql") from exc
    return PostgresOperatorRepository(lambda: psycopg.connect(dsn, connect_timeout=10))


if __name__ == "__main__":
    raise SystemExit(main())
