from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_work_actions_module_web import (
    patch_project_work_actions_module_response,
)


def test_work_actions_read_project_context_through_public_contract() -> None:
    script = patch_project_work_actions_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    ).body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert 'projectContext()?.current?.()' in script
    assert "window.FieldoraProjects?.currentProject" not in script
