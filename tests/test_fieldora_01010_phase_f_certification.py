import json
from pathlib import Path

from natureai_next.bootstrap.phase_f_certification_cli import main
from natureai_next.server.operations_evidence import (
    PHASE_F_EXERCISES,
    certification_status,
    record_exercise_evidence,
    write_certification_plan,
)


def test_plan_defines_every_exercise_without_claiming_results(tmp_path: Path) -> None:
    destination = write_certification_plan(
        tmp_path / "plan.json",
        environment_id="prod-a",
        release="0.10.10",
    )
    payload = json.loads(destination.read_text())
    assert [row["exercise"] for row in payload["exercises"]] == list(
        PHASE_F_EXERCISES
    )
    assert all(row["required_observations"] for row in payload["exercises"])
    assert "result" not in payload["exercises"][0]


def test_status_requires_all_passing_evidence_from_one_environment(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "provider.log"
    artifact.write_text("provider verified")
    evidence_root = tmp_path / "evidence"
    record_exercise_evidence(
        evidence_root,
        exercise="api-node-loss",
        environment_id="prod-a",
        executed_at_utc="2026-07-29T12:00:00Z",
        result="passed",
        objective="traffic continuity",
        observed="requests and PBAC denials continued",
        artifact=artifact,
        operator="operator-1",
    )
    report = certification_status(evidence_root, "prod-a")
    assert report["certification_status"] == "conditional"
    assert "api-node-loss" not in report["pending_exercises"]
    assert main(
        [
            "status",
            "--environment",
            "prod-a",
            "--evidence-root",
            str(evidence_root),
        ]
    ) == 2
