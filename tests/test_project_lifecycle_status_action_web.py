from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_lifecycle_module_web import (
    patch_project_lifecycle_module_response,
)


def test_lifecycle_status_change_uses_action_contract() -> None:
    patched = patch_project_lifecycle_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")
    module = script.split("WEB-PROJECT-LIFECYCLE-MODULE", 1)[1]

    assert 'resolveAction?.(name)' in module
    assert 'actionName==="projects.status.change"' in module
    assert "await action(state.editingId,body.expected_revision,body.status)" in module
    assert '"projects.status.change"' in module
    assert 'await mutate("",{expected_revision:project.revision,status:' in module
    assert '/status`' not in module
    assert '/archive`' in module
    assert 'method:"PATCH",purpose:"research"' in module
