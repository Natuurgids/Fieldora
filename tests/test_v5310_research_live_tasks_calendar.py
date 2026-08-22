from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_research_overview_embeds_live_project_tasks_and_calendar() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    research = source[source.index("class Research(Page):"):source.index("class DataTable")]
    assert "self.tasks=QTableWidget(0,4)" in research
    assert "self.calendar=QCalendarWidget()" in research
    assert "FROM pm_tasks t LEFT JOIN pm_statuses" in research
    assert "self.calendar.setSelectedDate(selected)" in research
    assert "('Projects & tasks'" not in research
    assert "('Calendar','Activities and deadlines'" not in research
    assert "self.compact_tools" in research
