from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.capacity_availability_module_web import (
    CapacityAvailabilityModuleWebApiMixin,
)
from natureai_next.server.capacity_legacy_retirement_web import (
    patch_capacity_legacy_retirement_response,
)
from natureai_next.server.capacity_module_web import patch_capacity_module_response
from natureai_next.server.dossier_module_web import patch_dossier_module_response
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server import modular_shell_web as shell


def _bundled_app() -> ApiResponse:
    app_path = (
        Path(__file__).parents[1]
        / "src"
        / "natureai_next"
        / "resources"
        / "server_web"
        / "app.js"
    )
    return ApiResponse(200, app_path.read_bytes(), "text/javascript; charset=utf-8")


def test_remaining_project_selectors_are_live_domain_inputs() -> None:
    script = _bundled_app().body.decode("utf-8")

    assert 'project_id:q("obs-project").value' in script
    assert 'project_id:q("knowledge-project").value' in script
    assert 'project_id:q("contract-project").value' in script
    assert 'project_id:q("device-project").value' in script


def test_managed_capacity_and_dossier_retirement_preserves_live_selectors() -> None:
    base = _bundled_app()
    allocation_owned = patch_capacity_module_response("/app.js", base)
    availability_owned = CapacityAvailabilityModuleWebApiMixin._patch_browser(
        "/app.js", allocation_owned
    )
    capacity_retired = patch_capacity_legacy_retirement_response(
        "/app.js", availability_owned
    )
    dossier_owned = patch_dossier_module_response("/app.js", capacity_retired)
    early_shell = shell.patch_modular_shell_response("/app.js", dossier_owned)
    final = patch_managed_web_response("/app.js", early_shell)
    script = final.body.decode("utf-8")

    assert '"capacity-project"' not in script.split("function projectOptions()", 1)[1].split("async function loadBase()", 1)[0]
    assert '"dossier-project"' not in script.split("function projectOptions()", 1)[1].split("async function loadBase()", 1)[0]
    for selector in (
        "obs-project",
        "knowledge-project",
        "contract-project",
        "device-project",
        "work-project",
        "science-project",
    ):
        assert f'"{selector}"' in script.split("function projectOptions()", 1)[1].split("async function loadBase()", 1)[0]

    assert 'project_id:q("obs-project").value' in script
    assert 'project_id:q("knowledge-project").value' in script
    assert 'project_id:q("contract-project").value' in script
    assert 'project_id:q("device-project").value' in script
