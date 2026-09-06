from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.web_module_contract_runtime import runtime_contract_manifest
from natureai_next.server.web_module_contracts import foundation_registry


def test_projects_core_consumes_declared_current_user_contract() -> None:
    projects = foundation_registry().resolve("/projects")
    assert projects is not None
    assert projects.requires_contracts == ("auth.current-user",)

    by_id = {item["module_id"]: item for item in runtime_contract_manifest()}
    assert by_id["projects.core"]["requires_contracts"] == ["auth.current-user"]

    script = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    ).body.decode("utf-8")

    assert 'resolve?.("auth.current-user")?.current?.()' in script
    assert "identity=currentUser()" in script
    assert "identity.identity_id" in script
    assert "me.identity_id" not in script
    assert 'typeof me!=="undefined"' not in script
