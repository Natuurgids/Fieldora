"""Operator CLI for verified one-node server recovery bundles."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.recovery import OneNodeServerRecovery


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldora-server-recovery")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--data-root", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--source", type=Path, required=True)
    restore = commands.add_parser("restore-to-new-root")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    validate = commands.add_parser("validate-restored-root")
    validate.add_argument("--data-root", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    recovery = OneNodeServerRecovery()
    if args.command == "backup":
        report = recovery.create(args.data_root, args.destination)
        print(f"Verified backup: {report.archive}")
    elif args.command == "verify":
        report = recovery.verify(args.source)
        print(f"Verified {report.files} files; SHA-256: {report.sha256}")
    elif args.command == "restore-to-new-root":
        target = recovery.restore_to_new_root(args.source, args.destination)
        print(f"Restored to new root: {target}")
    else:
        report = recovery.validate_restored_root(args.data_root, args.output)
        print(
            f"Restored root ready for Fieldora {report.fieldora_version}: "
            f"{len(report.databases)} databases"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
