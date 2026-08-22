import json
import subprocess
import sys
from pathlib import Path

from scripts.phase_d_exit_gate import evaluate


def test_phase_d_audit_distinguishes_implementation_from_certification() -> None:
    report = evaluate()
    assert report["phase"] == "D"
    assert report["release"] == "0.08.34"
    assert report["status"] == "conditional"
    assert report["failed"] == []
    assert report["blocked"] == [
        "live-postgresql",
        "live-object-search",
        "deployed-tls-client",
    ]


def test_phase_d_checker_is_fail_closed_and_can_emit_evidence(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"
    completed = subprocess.run(
        [sys.executable, "scripts/phase_d_exit_gate.py", "--output", str(output)],
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "conditional"
