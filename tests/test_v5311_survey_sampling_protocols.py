from __future__ import annotations

import json
import zipfile

import pytest

from natureai_next.application.project_management import ProjectExportOptions, ProjectManagementService


def test_project_survey_protocol_event_results_and_export(tmp_path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    project_id = service.create_project("Wetland survey", owner_id="lead", actor_id="lead")
    protocol_id = service.create_survey_protocol(
        project_id,
        name="Breeding bird point count",
        version=2,
        method="point count",
        description="Ten-minute stationary count.",
        target_group="birds",
        duration_minutes=10,
        equipment=("binoculars", "audio recorder"),
        required_fields=("weather", "effort", "observers"),
        actor_id="lead",
    )
    event_id = service.create_survey_event(
        project_id,
        name="North reedbed morning count",
        protocol_id=protocol_id,
        status="completed",
        start_text="2026-06-10 06:30",
        end_text="2026-06-10 06:40",
        latitude=52.1587,
        longitude=4.4972,
        location_name="Reedbed North",
        sampling_unit_type="station",
        sampling_unit_name="RN-01",
        duration_minutes=10,
        observers=("lead", "specialist"),
        weather={"wind_beaufort": 2, "cloud_percent": 20},
        habitat="reedbed",
        equipment=("binoculars",),
        actor_id="lead",
    )
    service.add_survey_detection(event_id, taxon_name="Reed Warbler", detected=True, count=3, actor_id="lead")
    service.add_survey_detection(event_id, taxon_name="Savi's Warbler", detected=False, actor_id="lead")

    protocol = service.survey_protocols(project_id)[0]
    assert protocol["version"] == 2
    assert protocol["equipment"] == ["binoculars", "audio recorder"]
    event = service.survey_events(project_id)[0]
    assert event["protocol_name"] == "Breeding bird point count"
    assert event["detected_count"] == 1
    assert event["non_detection_count"] == 1
    assert {row["detection_state"] for row in service.survey_detections(event_id)} == {"detected", "not_detected"}

    output = service.export_research_package(project_id, tmp_path / "survey.zip", options=ProjectExportOptions())
    with zipfile.ZipFile(output) as package:
        assert {"data/surveys.json", "data/surveys.csv"} <= set(package.namelist())
        payload = json.loads(package.read("data/surveys.json"))
        assert payload["events"][0]["location_name"] == "Reedbed North"
        assert len(payload["results"][event_id]) == 2


def test_survey_validation_and_project_ownership(tmp_path):
    service = ProjectManagementService(tmp_path / "projects.sqlite3")
    first = service.create_project("First", owner_id="lead", actor_id="lead")
    second = service.create_project("Second", owner_id="lead", actor_id="lead")
    protocol = service.create_survey_protocol(first, name="Transect", method="transect", actor_id="lead")
    with pytest.raises(ValueError, match="another project"):
        service.create_survey_event(second, name="Invalid", protocol_id=protocol, actor_id="lead")
    with pytest.raises(ValueError, match="latitude"):
        service.create_survey_event(first, name="Invalid", latitude=91, actor_id="lead")
    with pytest.raises(ValueError, match="does not exist"):
        service.create_survey_event(first, name="Invalid", protocol_id="missing", actor_id="lead")


def test_surveys_are_wired_from_research_to_project_workspace():
    desktop = open("src/natureai_next/ui/qt/v5_desktop.py", encoding="utf-8").read()
    application = open("src/natureai_next/ui/qt/application.py", encoding="utf-8").read()
    workspace = open("src/natureai_next/ui/qt/project_management.py", encoding="utf-8").read()
    assert "Surveys & sampling" in desktop
    assert "__project_surveys__" in desktop and "__project_surveys__" in application
    assert '"__project_surveys__:"' in application
    assert 'section = "Survey events" if prefix == "__project_surveys__:"' in application
    assert '"Surveys & Sampling"' in workspace
    assert "Record non-detection" in workspace
    assert '"include_surveys"' in workspace
