"""Create and assess fail-closed Phase F certification sessions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next import __version__
from natureai_next.server.operations_evidence import (
    certification_status,
    write_certification_plan,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-phase-f-certification")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--environment", required=True)
    plan.add_argument("--destination", type=Path, required=True)
    plan.add_argument("--release", default=__version__)
    status = commands.add_parser("status")
    status.add_argument("--environment", required=True)
    status.add_argument("--evidence-root", type=Path, required=True)
    status.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan":
        destination = write_certification_plan(
            args.destination,
            environment_id=args.environment,
            release=args.release,
        )
        print(destination)
        return 0
    report = certification_status(args.evidence_root, args.environment)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        if args.report.exists():
            raise FileExistsError(args.report)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix + ".tmp")
        try:
            temporary.write_text(rendered, encoding="utf-8")
            temporary.replace(args.report)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    print(rendered, end="")
    return 0 if report["certification_status"] == "passed" else 2
