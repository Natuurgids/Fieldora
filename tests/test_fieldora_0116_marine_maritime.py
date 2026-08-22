from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.application.marine_maritime import MarineMaritimeService
from natureai_next.application.science_capabilities import ScienceCapabilityService


def test_marine_and_maritime_records_are_separate_and_audited(tmp_path: Path) -> None:
    service = MarineMaritimeService(tmp_path / "marine-maritime.sqlite3")
    station = service.create(
        domain="marine",
        record_type="sampling_station",
        name="North Sea Station 14",
        latitude=54.5,
        longitude=3.2,
    )
    vessel = service.create(
        domain="maritime",
        record_type="vessel",
        name="RV Fieldora",
        status="active",
    )
    dive = service.create(
        domain="maritime",
        record_type="dive",
        name="Dive 14",
        depth_m=38.5,
        buddy="Alex Morgan",
    )

    assert [item.record_id for item in service.list("marine")] == [station.record_id]
    assert {item.record_id for item in service.list("maritime")} == {
        vessel.record_id,
        dive.record_id,
    }
    assert service.get(dive.record_id).depth_m == 38.5
    assert service.get(dive.record_id).buddy == "Alex Morgan"
    assert service.attach_assets(station.record_id, ("photo-1", "sound-1")) == 2
    assert service.attach_assets(station.record_id, ("photo-1",)) == 0
    assert service.attachment_ids(station.record_id) == ("photo-1", "sound-1")
    exported = service.export_records("marine")
    assert exported["contract"] == "fieldora.marine-maritime.v1"
    assert exported["records"][0]["asset_ids"] == ["photo-1", "sound-1"]


def test_record_types_are_domain_validated(tmp_path: Path) -> None:
    service = MarineMaritimeService(tmp_path / "marine-maritime.sqlite3")
    with pytest.raises(ValueError):
        service.create(domain="marine", record_type="vessel", name="Wrong domain")


def test_marine_modules_are_independently_switchable(tmp_path: Path) -> None:
    service = ScienceCapabilityService(tmp_path / "science.sqlite3")
    states = {item.capability_id: item for item in service.list()}
    assert states["science.marine"].enabled
    assert states["science.maritime"].enabled
    service.set_enabled("science.maritime", False)
    states = {item.capability_id: item for item in service.list()}
    assert states["science.marine"].enabled
    assert not states["science.maritime"].enabled


def test_desktop_shell_exposes_dedicated_workspaces() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert '"Marine & Freshwater Science": MarineMaritimeWorkspace(' in source
    assert '"Maritime Operations": MarineMaritimeWorkspace(' in source
    assert '"science.marine": "Marine & Freshwater Science"' in source
    assert '"science.maritime": "Maritime Operations"' in source


def test_submarine_log_and_research_navigation_are_explicit() -> None:
    workspace = Path("src/natureai_next/ui/qt/marine_maritime.py").read_text(
        encoding="utf-8"
    )
    application = Path("src/natureai_next/ui/qt/application.py").read_text(
        encoding="utf-8"
    )
    assert '"submarine_log": "Submarine Logs"' in workspace
    research_start = application.index('research_menu: QMenu')
    records_start = application.index('records_menu = research_menu', research_start)
    assert '"Maritime Operations", "Maritime Operations"' in application[
        research_start:records_start
    ]
    assert '"Depth (m)"' in workspace
    assert '"Buddy / dive partner"' in workspace
