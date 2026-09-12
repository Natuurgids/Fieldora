from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_work_actions_module_web import (
    patch_project_work_actions_module_response,
)


def test_work_actions_owner_retires_legacy_work_editor_dom() -> None:
    script = patch_project_work_actions_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    ).body.decode("utf-8")

    assert 'const legacyEditor=q("work-save")?.closest(".card.section")' in script
    assert "if(legacyEditor)legacyEditor.remove()" in script
