import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from natureai_next.application.project_management import ProjectManagementService
from natureai_next.ui.qt.v5_desktop import MeasurementsSampling


def app():
    return QApplication.instance() or QApplication([])


def test_workspace_shows_data_and_applies_project_permissions(tmp_path: Path):
    app()
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    project = service.create_project("Bird study", owner_id="owner", actor_id="owner")
    service.create_survey_protocol(project, name="Bird count", method="point count", target_group="birds", actor_id="owner")
    service.create_sample(project, sample_code="B-001", sample_type="feather", latitude=1, longitude=2, actor_id="owner")
    service.set_member_role(project, "viewer", "guest", actor_id="owner")

    page = MeasurementsSampling(database, actor_provider=lambda: "viewer")
    page.select_project(project, section="Protocols")
    assert page.protocols.rowCount() == 1
    assert page.samples.rowCount() == 1
    assert page.protocols.item(0, 0).text() == "Bird count"
    assert page.samples.item(0, 0).text() == "B-001"
    assert page.action_buttons["newProtocolButton"].isVisible()
    assert not page.action_buttons["newProtocolButton"].isEnabled()

    page.actor_provider = lambda: "owner"
    page.refresh()
    page.select_project(project, section="Protocols")
    assert page.action_buttons["newProtocolButton"].isVisible()
    assert page.action_buttons["newProtocolButton"].isEnabled()
    assert not page.action_buttons["newSampleButton"].isVisible()


def test_every_workspace_action_has_a_connected_receiver(tmp_path: Path):
    app()
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    project = service.create_project("Study", owner_id="owner", actor_id="owner")
    page = MeasurementsSampling(database, actor_provider=lambda: "owner")
    page.select_project(project, section="Specimens")

    assert set(page.action_buttons) == {
        "newSpecimenButton", "identifierButton", "newEncounterButton",
        "specimenTimelineButton", "mergeSpecimensButton", "newProtocolButton",
        "newSurveyEventButton", "newSampleButton", "recordEnrichmentButton",
        "templatesButton", "custodyEventButton", "laboratoryRecordButton",
        "laboratoryMediaButton", "changeStatusButton", "qualityChecksButton",
    }
    assert all(button.receivers(button.clicked) > 0 for button in page.action_buttons.values())


def test_context_toolbar_changes_with_selected_tab(tmp_path: Path):
    app()
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    project = service.create_project("Study", owner_id="owner", actor_id="owner")
    page = MeasurementsSampling(database, actor_provider=lambda: "owner")
    page.select_project(project, section="Protocols")
    assert page.action_buttons["newProtocolButton"].isVisible()
    assert page.action_buttons["templatesButton"].isVisible()
    assert not page.action_buttons["newSampleButton"].isVisible()

    page.select_project(project, section="Samples")
    assert page.action_buttons["newSampleButton"].isVisible()
    assert page.action_buttons["custodyEventButton"].isVisible()
    assert not page.action_buttons["newProtocolButton"].isVisible()
