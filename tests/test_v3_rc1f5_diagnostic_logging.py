from __future__ import annotations

import json

from natureai_next.infrastructure.ai.diagnostic_logging import (
    DiagnosticSettings,
    log_path,
    save_settings,
    write_event,
    write_exception,
)


def test_diagnostic_logging_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("APERTURE_DATA_ROOT", str(tmp_path))
    save_settings(DiagnosticSettings(False, "detailed"))
    write_event("hidden")
    assert not log_path().exists()


def test_diagnostic_logging_records_error_under_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("APERTURE_DATA_ROOT", str(tmp_path))
    save_settings(DiagnosticSettings(True, "detailed"))
    try:
        raise ValueError("unknown taxon")
    except ValueError as exc:
        write_exception("inference-item-failed", exc, run_id="r1", asset_id="a1", stage="persist")
    row = json.loads(log_path().read_text(encoding="utf-8").splitlines()[0])
    assert row["exception_type"] == "ValueError"
    assert row["stage"] == "persist"
    assert "traceback" in row
    assert str(log_path()).startswith(str(tmp_path))
