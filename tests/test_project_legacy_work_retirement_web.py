from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_list_provider_web import patch_project_list_provider_response
from natureai_next.server.project_work_actions_module_web import (
    patch_project_work_actions_module_response,
)
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)


def _finalize_context(response: ApiResponse) -> str:
    shell = patch_modular_shell_response("/app.js", response)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    listed = patch_project_list_provider_response("/app.js", contracts)
    return patch_project_context_provider_response("/app.js", listed).body.decode("utf-8")


def test_legacy_work_editor_is_preserved_without_modular_owner() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options="";["work-project","science-project"].forEach(id=>id)}'
            'async function saveWorkItem(){const legacyEditor=true;}'
            'async function loadCapacity(){const neighboringCapacity=true;}'
            'q("work-save").onclick=saveWorkItem;'
        ).encode(),
        "text/javascript; charset=utf-8",
    )

    script = _finalize_context(legacy)

    assert "async function saveWorkItem(){" in script
    assert 'q("work-save").onclick=saveWorkItem;' in script
    assert '"work-project","science-project"' in script
    assert "async function loadCapacity(){" in script


def test_modular_work_actions_owner_retires_only_legacy_work_editor() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options="";["work-project","science-project"].forEach(id=>id)}'
            'async function saveWorkItem(){const legacyEditor=true;}'
            'async function loadCapacity(){const neighboringCapacity=true;}'
            'q("work-save").onclick=saveWorkItem;'
            'q("science-save").onclick=saveScienceRecord;'
        ).encode(),
        "text/javascript; charset=utf-8",
    )
    owned = patch_project_work_actions_module_response("/app.js", legacy)

    script = _finalize_context(owned)

    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert "async function saveWorkItem(){" not in script
    assert "const legacyEditor=true" not in script
    assert 'q("work-save").onclick=saveWorkItem;' not in script
    assert '"work-project","science-project"' not in script
    assert '"science-project"' in script
    assert "async function loadCapacity(){" in script
    assert "const neighboringCapacity=true" in script
    assert 'q("science-save").onclick=saveScienceRecord;' in script


def test_real_app_final_context_removes_legacy_work_editor_and_keeps_neighbors() -> None:
    body = Path("src/natureai_next/resources/server_web/app.js").read_bytes()
    response = ApiResponse(200, body, "text/javascript; charset=utf-8")
    owned = patch_project_work_actions_module_response("/app.js", response)

    script = _finalize_context(owned)

    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert "async function saveWorkItem(){" not in script
    assert 'q("work-save").onclick=saveWorkItem;' not in script
    assert '"work-project","science-project"' not in script
    assert "async function loadCapacity(){" in script
    assert 'q("capacity-save").onclick=saveCapacity;' in script
    assert 'q("science-save").onclick=saveScienceRecord;' in script
