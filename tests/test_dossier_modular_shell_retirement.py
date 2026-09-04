from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_module_web import patch_dossier_module_response
from natureai_next.server import modular_shell_web as shell


def _legacy_dossier_response() -> ApiResponse:
    body = (
        b"async function loadDossierWorkspace(){const legacyLoad=true;}"
        b"async function saveDossierWorkspace(){const legacySave=true;}"
        b"async function loadResearchDomain(){}"
        b'q("dossier-refresh").onclick=loadDossierWorkspace;'
        b'q("dossier-save").onclick=saveDossierWorkspace;'
        + shell._LEGACY_DOSSIER_LIST_WIRING
    )
    return ApiResponse(200, body, "text/javascript; charset=utf-8")


def test_dossier_owner_does_not_retire_legacy_workspace_without_registry_ownership(
    monkeypatch,
) -> None:
    unregistered_bootstrap = shell._MODULAR_SHELL_BOOTSTRAP.replace(
        shell._DOSSIER_REGISTRY_MARKER, b"", 1
    )
    monkeypatch.setattr(shell, "_MODULAR_SHELL_BOOTSTRAP", unregistered_bootstrap)

    owned = patch_dossier_module_response("/app.js", _legacy_dossier_response())
    final = shell.patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert "WEB-DOSSIER-MODULE" in script
    assert '"module_id":"dossiers.workspace"' not in script
    assert "async function loadDossierWorkspace(){" in script
    assert "async function saveDossierWorkspace(){" in script
    assert 'q("dossier-refresh").onclick=loadDossierWorkspace;' in script
    assert 'q("dossier-save").onclick=saveDossierWorkspace;' in script
    assert shell._LEGACY_DOSSIER_LIST_WIRING.decode("utf-8") in script


def test_registered_dossier_owner_retires_only_legacy_workspace_competitors() -> None:
    assert shell._DOSSIER_REGISTRY_MARKER in shell._MODULAR_SHELL_BOOTSTRAP

    owned = patch_dossier_module_response("/app.js", _legacy_dossier_response())
    final = shell.patch_modular_shell_response("/app.js", owned)
    script = final.body.decode("utf-8")

    assert "WEB-DOSSIER-MODULE" in script
    assert '"module_id":"dossiers.workspace"' in script
    assert "async function loadDossierWorkspace(){" not in script
    assert "async function saveDossierWorkspace(){" not in script
    assert 'q("dossier-refresh").onclick=loadDossierWorkspace;' not in script
    assert 'q("dossier-save").onclick=saveDossierWorkspace;' not in script
    assert shell._LEGACY_DOSSIER_LIST_WIRING.decode("utf-8") not in script
    assert "async function loadResearchDomain(){}" in script
