import json
from pathlib import Path

from natureai_next.server.production_recovery import (
    assess_recovery_file,
    assess_recovery_plan,
)


def test_reference_recovery_contract_is_ready(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    report = tmp_path / "recovery.json"
    result = assess_recovery_file(
        root / "deployment/reference-recovery.json", report
    )
    assert result.recovery_ready
    assert result.rpo_seconds == 300
    assert result.rto_seconds == 3600
    assert json.loads(report.read_text())["recovery_ready"] is True


def test_recovery_contract_fails_closed_on_unsafe_restore() -> None:
    result = assess_recovery_plan(
        {
            "format": "fieldora.production-recovery",
            "format_version": 1,
            "environment_id": "production",
            "objectives": {"rpo_seconds": 3600, "rto_seconds": 7200},
            "postgresql": {"restore_to_new_target": False},
            "object_storage": {"legal_holds_preserved": False},
            "search": {"rebuild_from_authority": False},
            "key_custody": {"provider": "inline"},
            "drills": {"source_untouched": False},
        }
    )
    assert not result.recovery_ready
    codes = {issue.code for issue in result.issues}
    assert {
        "objectives.rpo",
        "objectives.rto",
        "postgres.restore_target",
        "objects.legal_holds",
        "search.authority",
        "keys.provider",
        "drills.non_destructive",
    } <= codes
