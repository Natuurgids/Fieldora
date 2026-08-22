from scripts.phase_e_exit_gate import evaluate


def test_phase_e_exit_gate_passes_deterministic_evidence() -> None:
    report = evaluate()
    assert report["release"] == "0.11.21"
    assert report["status"] == "pass"
    assert all(item["status"] == "pass" for item in report["checks"])
