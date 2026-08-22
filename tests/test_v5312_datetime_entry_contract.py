from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_datetime_field_has_direct_entry_calendar_and_explicit_apply():
    source = (ROOT / "src/natureai_next/ui/qt/date_time_input.py").read_text(encoding="utf-8")
    assert "QLineEdit" in source
    assert "QDateTimeEdit" in source
    assert "setCalendarPopup(True)" in source
    assert "Use selected date and time" in source
    assert "QDateTime.currentDateTime()" in source


def test_operational_datetime_prompts_use_shared_picker():
    source = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    expected = (
        "Applied date/time",
        "Occurred date/time",
        "Start date/time",
        "Collected date/time",
        "Effective date/time",
        "Captured date/time",
        "Calibrated date/time",
    )
    for label in expected:
        assert label in source
    assert source.count("get_datetime_text(") >= 8


def test_legacy_project_and_maritime_date_entry_use_shared_widget():
    project = (ROOT / "src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    maritime = (ROOT / "src/natureai_next/ui/qt/marine_maritime.py").read_text(encoding="utf-8")
    assert "get_datetime_text" in project
    assert "DateTimeTextField" in maritime
    assert 'setPlaceholderText("ISO date/time")' not in maritime
