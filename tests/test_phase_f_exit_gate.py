import hashlib
import json
from pathlib import Path

from scripts.phase_f_exit_gate import evaluate


def test_phase_f_gate_is_implementation_ready_and_certification_conditional() -> None:
    report = evaluate()
    assert report["phase"] == "F"
    assert report["release"] == "5.4.0"
    assert report["implementation_ready"] is True
    assert report["certification_status"] == "conditional"
    assert "zone-failure" in report["pending_exercises"]


def test_phase_f_gate_closes_only_with_all_passing_exercises(tmp_path: Path) -> None:
    for exercise in evaluate()["pending_exercises"]:
        artifact = tmp_path / f"{exercise}.artifact"
        artifact.write_bytes(exercise.encode())
        payload = {
            "format": "fieldora.phase-f-exercise-evidence",
            "exercise": exercise,
            "environment_id": "certification",
            "executed_at_utc": "2026-07-29T12:00:00Z",
            "result": "passed",
            "objective": "published objective",
            "observed": "objective met",
            "artifact_file": artifact.name,
            "artifact_sha256": hashlib.sha256(exercise.encode()).hexdigest(),
            "operator": "certification-operator",
        }
        (tmp_path / f"{exercise}.json").write_text(json.dumps(payload))
    report = evaluate(tmp_path)
    assert report["certification_status"] == "passed"
    assert report["pending_exercises"] == []
