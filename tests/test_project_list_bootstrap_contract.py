from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_capabilities import patch_zero_trust_web_response


def test_modular_project_bootstrap_uses_list_contract_before_legacy_fallback() -> None:
    patched = patch_zero_trust_web_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    contract = "window.FieldoraModuleContracts?.resolve?.('projects.list.read')"
    contract_refresh = "const items=await list.refresh();projects=items.map(item=>({...item}));"
    fallback = "const result=await baseApi('/api/v1/projects');projects=result.items||[];"

    assert contract in script
    assert contract_refresh in script
    assert fallback in script
    assert script.index(contract) < script.index(contract_refresh) < script.index(fallback)


def test_project_bootstrap_keeps_legacy_projects_as_mirror_not_authoritative_source() -> None:
    patched = patch_zero_trust_web_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = patched.body.decode("utf-8")

    assert "projects=[];" in script
    assert "projects=items.map(item=>({...item}))" in script
    assert "projectOptions();" in script
