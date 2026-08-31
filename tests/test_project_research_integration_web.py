from __future__ import annotations

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
    assert research.dependencies == ("projects.core",)


def test_project_research_adapter_is_idempotent_and_uses_public_contracts() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    patched = patch_project_research_integration_response("/app.js", original)
    again = patch_project_research_integration_response("/app.js", patched)

    assert patched.body == again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-RESEARCH-INTEGRATION" in script
    assert 'ownerModule="research.dossiers"' in script
    assert 'projectModule="projects.core"' in script
    assert '<button id="project-open-research"' not in script
    assert 'button.id="project-open-research"' in script
    assert 'button.dataset.fieldoraAction="research.project.open"' in script
    assert 'navigate?.("/research","project-research-integration","push")' in script
    assert "window.FieldoraProjects?.currentProject?.()" in script
    assert "window.FieldoraResearchRecords" in script
    assert "science-project" not in script
    assert "loadResearchDomain" not in script


def test_research_records_exposes_project_context_bridge() -> None:
    response = patch_research_records_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")

    assert "integrationProjectId" in script
    assert "async function openProject(projectId)" in script
    assert "window.FieldoraResearchRecords=Object.freeze" in script
    assert "?project_id=${encodeURIComponent(project)}" in script


def test_project_research_integration_is_composed_inside_shell() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert mro[2] is ProjectResearchIntegrationWebApiMixin


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert (
        patch_project_research_integration_response("/api/v1/projects", original)
        is original
    )
