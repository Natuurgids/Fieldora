"""Installed CLI for Phase F production deployment assessment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.production_deployment import assess_file


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldora-deployment-assessment")
    parser.add_argument("deployment", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    assessment = assess_file(args.deployment, args.report)
    print(json.dumps(assessment.as_dict(), indent=2, sort_keys=True))
    return 0 if assessment.configuration_ready else 1
