"""Installed production recovery assessment CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.production_recovery import assess_recovery_file


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldora-recovery-assessment")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    assessment = assess_recovery_file(args.plan, args.report)
    print(json.dumps(assessment.as_dict(), indent=2, sort_keys=True))
    return 0 if assessment.recovery_ready else 1
