from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_composition import finalize_modular_shell_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response


def test_portfolio_owner_retires_legacy_cross_screen_open_project_wiring() -> None:
    response = ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
    response = patch_navigation_web_response("/app.js", response)
    response = patch_portfolio_module_response("/app.js", response)
    installed = patch_modular_shell_response("/app.js", response)
    final = finalize_modular_shell_response("/app.js", installed)
    script = final.body.decode("utf-8")

    assert "WEB-PORTFOLIO-MODULE" in script
    assert 'navigator.navigate("/projects",moduleId,"push")' in script
    assert 'data-open-project-workspace' not in script
    assert 'open.onclick=()=>openProject(id)' not in script
    assert 'openProject(row.dataset.portfolioId)' not in script

    # Operations now owns its related-project affordance through public contracts.
    assert "WEB-OPERATIONS-RELATED-PROJECT" in script
    assert 'host.records?.()' in script
    assert 'const operations=q("operations-list")' not in script
    assert 'open.onclick=()=>openProject(item.project_id)' not in script
