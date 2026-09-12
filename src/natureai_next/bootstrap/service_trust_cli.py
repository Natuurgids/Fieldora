"""CLI for installation-local Fieldora service mutual-TLS identities."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from natureai_next.server.service_trust import ServiceTrustAuthority


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-service-trust")
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init-ca")
    initialize.add_argument("--common-name", default="Fieldora Internal Service CA")
    issue = commands.add_parser("issue")
    issue.add_argument("--service-id", required=True)
    issue.add_argument("--organization", required=True)
    issue.add_argument("--common-name", required=True)
    issue.add_argument("--certificate", type=Path, required=True)
    issue.add_argument("--private-key", type=Path, required=True)
    issue.add_argument("--dns", action="append", default=[])
    issue.add_argument("--ip", action="append", default=[])
    issue.add_argument("--hours", type=int, default=168)
    issue.add_argument("--new-private-key", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--certificate", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    authority = ServiceTrustAuthority(args.root)
    if args.command == "init-ca":
        print(authority.initialize(args.common_name))
        return 0
    if args.command == "issue":
        record = authority.issue(
            service_id=args.service_id,
            organization_id=args.organization,
            common_name=args.common_name,
            certificate_path=args.certificate,
            private_key_path=args.private_key,
            dns_names=tuple(args.dns),
            ip_addresses=tuple(args.ip),
            lifetime_hours=args.hours,
            reuse_private_key=not args.new_private_key,
        )
        print(
            json.dumps(
                {
                    "service_id": record.service_id,
                    "organization_id": record.organization_id,
                    "serial_number": record.serial_number,
                    "not_after_utc": record.not_after_utc,
                    "not_after_epoch": int(
                        datetime.fromisoformat(record.not_after_utc).timestamp()
                    ),
                    "certificate": str(record.certificate_path),
                    "private_key": str(record.private_key_path),
                    "ca_certificate": str(record.ca_certificate_path),
                },
                sort_keys=True,
            )
        )
        return 0
    record = authority.inspect(args.certificate)
    print(
        json.dumps(
            {
                "service_id": record.service_id,
                "organization_id": record.organization_id,
                "serial_number": record.serial_number,
                "not_before_utc": record.not_before_utc,
                "not_after_utc": record.not_after_utc,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
