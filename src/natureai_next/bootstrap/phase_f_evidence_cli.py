"""Record a verified Phase F infrastructure exercise."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from natureai_next.server.operations_evidence import (
    PHASE_F_EXERCISES,
    record_exercise_evidence,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldora-record-phase-f-evidence")
    parser.add_argument("exercise", choices=PHASE_F_EXERCISES)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--executed-at-utc", required=True)
    parser.add_argument("--result", choices=("passed", "failed"), required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--observed", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--operator", required=True)
    args = parser.parse_args(argv)
    path = record_exercise_evidence(
        args.evidence_root,
        exercise=args.exercise,
        environment_id=args.environment,
        executed_at_utc=args.executed_at_utc,
        result=args.result,
        objective=args.objective,
        observed=args.observed,
        artifact=args.artifact,
        operator=args.operator,
    )
    print(path)
    return 0
