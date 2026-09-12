from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_compatibility import patch_web_response


def test_compatibility_keeps_project_list_mirror_without_dossier_context_ownership() -> None:
    response = patch_web_response(
        "/app.js",
        ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "function syncLegacyProjectsFromListContract()" in script
    assert 'resolve?.("projects.list.read")' in script
    assert "projects=Array.from(list.items()||[],item=>({...item}));projectOptions();" in script
    assert (
        'document.addEventListener("fieldora:project-list-changed",syncLegacyProjectsFromListContract);'
        in script
    )

    assert "currentProjectContext" not in script
    assert "syncLegacyDossierProjectSelector" not in script
    assert 'resolve?.("projects.context.select")' not in script
    assert 'q("dossier-project")' not in script
    assert 'document.addEventListener("fieldora:project-context-changed"' not in script
