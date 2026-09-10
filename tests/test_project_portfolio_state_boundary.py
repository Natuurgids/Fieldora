from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)


def test_project_core_final_composition_does_not_read_portfolio_private_datasets() -> None:
    response = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    response = patch_project_facility_workspace_response("/app.js", response)
    response = patch_project_core_module_response("/app.js", response)
    response = patch_portfolio_module_response("/app.js", response)
    final = patch_modular_shell_response("/app.js", response)
    script = final.body.decode("utf-8")

    assert "WEB-PROJECT-CORE-MODULE" in script
    assert "WEB-PORTFOLIO-MODULE" in script
    assert 'resolve?.("projects.work-data.service")' in script
    assert "const snapshot=await service.load(state.projectId)" in script

    # Projects must not reconstruct work state from Portfolio-owned DOM datasets.
    assert "function portfolioData()" not in script
    assert 'JSON.parse(q("portfolio-list")?.dataset.tasks' not in script
    assert 'JSON.parse(q("portfolio-list").dataset[kind==="phase"?"phases":"tasks"]' not in script

    # Portfolio may still own its private rendering cache in this bounded slice.
    assert "list.dataset.tasks=JSON.stringify(tasks.items||[])" in script

    # Project cockpit DOM reparenting is a separate A07 concern and stays untouched.
    assert "if(detailCard)props.appendChild(detailCard)" in script
