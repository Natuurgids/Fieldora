from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_compatibility import patch_web_response


def test_legacy_dossier_project_selector_tracks_canonical_context() -> None:
    response = patch_web_response(
        "/app.js",
        ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert (
        'function currentProjectContext(){return window.FieldoraModuleContracts?.resolve?.("projects.context.select")?.current?.()||"";}'
        in script
    )
    start = script.index("function syncLegacyDossierProjectSelector()")
    end = script.index("function syncLegacyProjectsFromListContract()", start)
    bridge = script[start:end]
    assert 'q("dossier-project")' in bridge
    assert "projects[0]" not in bridge

    assert "projectOptions();syncLegacyDossierProjectSelector();" in script
    assert (
        'document.addEventListener("fieldora:project-context-changed",syncLegacyDossierProjectSelector);'
        in script
    )
    assert (
        'event.detail?.contract==="projects.context.select")syncLegacyDossierProjectSelector();'
        in script
    )
