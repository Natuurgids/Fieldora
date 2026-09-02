from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import patch_browser_functionality_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.project_creation_module_web import (
    ProjectCreationModuleWebApiMixin,
    patch_project_creation_module_response,
)
from natureai_next.server.web_module_contracts import foundation_registry


def test_projects_core_owns_top_level_create_action() -> None:
    owner = foundation_registry().action_owner("projects.create")

    assert owner is not None
    assert owner.module_id == "projects.core"


def test_creation_adapter_is_idempotent_and_not_portfolio_coupled() -> None:
    original = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")

    patched = patch_project_creation_module_response("/app.js", original)
    patched_again = patch_project_creation_module_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert "WEB-PROJECT-CREATION-MODULE" in script
    assert "window.FieldoraProjectCreation" in script
    assert 'id="project-core-create-editor"' in script
    assert 'api("/api/v1/projects",{method:"POST",purpose:"research"' in script
    assert "loadPortfolio" not in script
    assert "portfolio-new-project" not in script
    assert "showPage=" not in script


def test_creation_refresh_requires_project_list_contract() -> None:
    patched = patch_project_creation_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.list.read")' in script
    assert 'if(!projectList?.refresh)throw new Error("Project list contract is unavailable.")' in script
    assert "const items=await projectList.refresh()" in script
    assert '(await api("/api/v1/projects",{purpose:"research"})).items||[]' not in script
    assert "projects=Array.from(items||[],item=>({...item}))" in script
    assert "window.FieldoraProjectList" not in script


def test_creation_selects_created_project_through_context_contract() -> None:
    patched = patch_project_creation_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert "if(selectedId&&projectContext?.select)await projectContext.select(selectedId)" in script
    assert "window.FieldoraProjects?.selectProject" not in script


def test_creation_validation_and_server_owned_defaults_are_explicit() -> None:
    patched = patch_project_creation_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "Project name is required." in script
    assert "Project due date must not be before start date." in script
    assert "Budget must be zero or greater." in script
    assert "Ownership is assigned to the authenticated creator by the server." in script
    assert "status:" not in script
    assert "owner_id" not in script


def test_final_shell_removes_only_legacy_project_creation_fragment() -> None:
    base = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    legacy = patch_browser_functionality_response("/app.js", base)
    owned = patch_project_creation_module_response("/app.js", legacy)

    before = owned.body.decode("utf-8")
    assert "Project creation belongs in Projects & Portfolio" in before
    assert "uploadSelectedFiles" in before
    assert "mediaPreview" in before

    final = patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-CREATION-MODULE" in script
    assert "Project creation belongs in Projects & Portfolio" not in script
    assert "portfolio-new-project" not in script
    assert "uploadSelectedFiles" in script
    assert "mediaPreview" in script


def test_creation_mixin_is_inside_modular_shell_and_outside_project_core() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert mro[1].__name__ == "ModularShellWebApiMixin"
    assert ProjectCreationModuleWebApiMixin in mro
    assert mro.index(ProjectCreationModuleWebApiMixin) < mro.index(
        next(base for base in mro if base.__name__ == "ProjectCoreModuleWebApiMixin")
    )


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert patch_project_creation_module_response("/api/v1/status", original) is original
