from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_research_integration_web import (
    ProjectResearchIntegrationWebApiMixin,
    patch_project_research_integration_response,
)
from natureai_next.server.research_records_web import patch_research_records_response
from natureai_next.server.web_module_contracts import foundation_registry


def test_research_owns_project_integration_actions() -> None:
    registry = foundation_registry()
    research = registry.action_owner("research.project.open")
    records = registry.action_owner("research.project.records.view")

    assert research is not None
    assert records is research
    assert research.module_id == "research.dossiers"
    assert research.dependencies == ()
    assert research.requires_contracts == (
        "projects.context.select",
        "projects.toolbar.extend",
    )


def test_project_research_adapter_uses_replaceable_projects_contracts() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_project_research_integration_response("/app.js", original)
    again = patch_project_research_integration_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-RESEARCH-INTEGRATION" in script
    assert 'ownerModule="research.dossiers"' in script
    assert 'entryKey="research.project.open"' in script
    assert 'resolve?.("projects.context.select")' in script
    assert 'resolve?.("projects.toolbar.extend")' in script
    assert "projectContext()?.current?.()" in script
    assert "projectToolbar()?.setEnabled?." in script
    assert 'toolbar.upsert({key:entryKey,label:"Open research"' in script
    assert 'action:"research.project.open"' in script
    assert 'navigate?.("/research","project-research-integration","push")' in script
    assert 'name==="projects.context.select"' in script
    assert 'name==="projects.toolbar.extend"' in script
    assert "projects.core" not in script
    assert "project-desktop-cockpit" not in script
    assert "document.createElement" not in script
    assert "window.FieldoraProjects" not in script
    assert "window.FieldoraResearchRecords" in script
    assert "science-project" not in script
    assert "loadResearchDomain" not in script


def test_research_project_open_uses_project_context_contract() -> None:
    response = patch_project_research_integration_response(
        "/app.js",
        ApiResponse(
            200,
            b'function openProject(id){selectedProject=id;showPage("research")}',
            "text/javascript; charset=utf-8",
        ),
    )
    script = response.body.decode("utf-8")
    adapter = script.split("/* WEB-PROJECT-RESEARCH-INTEGRATION", 1)[1]

    assert 'const legacyOpenProject=typeof openProject==="function"?openProject:null' in adapter
    assert "async function openResearchProject(id)" in adapter
    assert "const context=projectContext()" in adapter
    assert "await context.select(pid)" in adapter
    assert "if(selected===false)return false" in adapter
    assert "if(legacyOpenProject)legacyOpenProject(pid)" in adapter
    assert "await applyResearchProject()" in adapter
    assert "selectedProject" not in adapter
    assert 'if(legacyOpenProject)openProject=openResearchProject' in adapter
    assert "openSelectedProject,openResearchProject,applyResearchProject" in adapter


def test_research_export_uses_project_context_contract() -> None:
    response = patch_project_research_integration_response(
        "/app.js",
        ApiResponse(
            200,
            b"async function exportProject(){if(!selectedProject)return;}",
            "text/javascript; charset=utf-8",
        ),
    )
    script = response.body.decode("utf-8")
    adapter = script.split("/* WEB-PROJECT-RESEARCH-INTEGRATION", 1)[1]

    assert "async function exportCurrentProject()" in adapter
    assert "const pid=currentProject()" in adapter
    assert 'resolve?.("projects.context.select")' in adapter
    assert "project_id:pid" in adapter
    assert "selectedProject" not in adapter
    assert 'if(typeof exportProject==="function")exportProject=exportCurrentProject' in adapter


def test_research_record_editor_uses_project_context_contract() -> None:
    response = patch_project_research_integration_response(
        "/app.js",
        ApiResponse(
            200,
            b'function editRecord(kind){q("record-project").value=selectedProject||""}',
            "text/javascript; charset=utf-8",
        ),
    )
    script = response.body.decode("utf-8")
    adapter = script.split("/* WEB-PROJECT-RESEARCH-INTEGRATION", 1)[1]

    assert "function editResearchRecord(kind)" in adapter
    assert 'q("record-project").value=kind==="project"?"":currentProject()' in adapter
    assert 'resolve?.("projects.context.select")' in adapter
    assert "selectedProject" not in adapter
    assert 'if(typeof editRecord==="function")editRecord=editResearchRecord' in adapter
    assert "editResearchRecord,exportCurrentProject" in adapter


def test_legacy_record_project_selector_remains_required_by_generic_record_save() -> None:
    script = Path("src/natureai_next/resources/server_web/app.js").read_text(
        encoding="utf-8"
    )

    assert 'q("record-project").value=selectedProject||""' in script
    assert 'project=q("record-project").value' in script
    assert 'project_id:kind==="project"?undefined:project' in script

    response = patch_project_research_integration_response(
        "/app.js", ApiResponse(200, script.encode("utf-8"), "text/javascript; charset=utf-8")
    )
    adapter = response.body.decode("utf-8").split(
        "/* WEB-PROJECT-RESEARCH-INTEGRATION", 1
    )[1]

    assert 'q("record-project").value=kind==="project"?"":currentProject()' in adapter
    assert "selectedProject" not in adapter


def test_research_records_exposes_project_context_bridge() -> None:
    response = patch_research_records_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")

    assert "integrationProjectId" in script
    assert 'resolve?.("projects.context.select")' in script
    assert "projectContext()?.current?.()" in script
    assert "selectedProject" not in script
    assert "async function openProject(projectId)" in script
    assert "window.FieldoraResearchRecords=Object.freeze" in script
    assert "?project_id=${encodeURIComponent(project)}" in script


def test_project_research_integration_is_composed_inside_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert ProjectResearchIntegrationWebApiMixin in mro[2:]


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert (
        patch_project_research_integration_response("/api/v1/projects", original)
        is original
    )
