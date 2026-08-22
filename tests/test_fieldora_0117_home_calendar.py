from __future__ import annotations

import ast
from pathlib import Path

from natureai_next.application.calendar_interop import CalendarEvent, CalendarInteropService


def test_calendar_export_and_provider_links(tmp_path: Path) -> None:
    event = CalendarEvent(
        event_id="event-1",
        title="Water sampling",
        event_date="2026-08-03",
        description="Station 14",
    )
    destination = CalendarInteropService().export_ics((event,), tmp_path / "fieldora.ics")
    content = destination.read_text(encoding="utf-8")

    assert "BEGIN:VCALENDAR" in content
    assert "DTSTART;VALUE=DATE:20260803" in content
    assert "SUMMARY:Water sampling" in content
    assert "calendar.google.com" in CalendarInteropService.google_create_url(event)
    assert "outlook.office.com" in CalendarInteropService.outlook_create_url(event)


def test_calendar_count_widget_is_used_by_both_calendars() -> None:
    science = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    projects = Path("src/natureai_next/ui/qt/project_management.py").read_text(
        encoding="utf-8"
    )
    assert "self._calendar = ActivityCountCalendar()" in science
    assert "self._calendar.set_activity_counts(counts)" in science
    assert "self._calendar = ActivityCountCalendar()" in projects
    assert "self._calendar.set_activity_counts(counts)" in projects


def test_desktop_starts_on_home_workspace() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert '("Overview", (' in source
    assert '("Home", "Home")' in source
    assert 'self._select_workspace("Home")' in source
    assert "self._home_workspace = HomeWorkspace(" in source


def test_navigation_root_contains_only_branches() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    navigation = next(
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "navigation" for target in node.targets)
    )
    for _root_label, branches in navigation:
        for _branch_label, children in branches:
            assert isinstance(children, tuple)
            assert all(isinstance(child, tuple) and len(child) == 2 for child in children)
