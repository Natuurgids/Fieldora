from __future__ import annotations

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


_PROJECT_MIRROR = 'if(q("work-project"))q("work-project").value=state.projectId;'


def _finalize_context(response: ApiResponse) -> str:
    shell = patch_modular_shell_response("/app.js", response)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    listed = patch_project_list_provider_response("/app.js", contracts)
    return patch_project_context_provider_response("/app.js", listed).body.decode("utf-8")


def test_work_project_context_mirror_remains_without_modular_work_owner() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options="";["work-project","science-project"].forEach(id=>id)}'
            + _PROJECT_MIRROR
        ).encode(),
        "text/javascript; charset=utf-8",
    )

    script = _finalize_context(legacy)

    assert _PROJECT_MIRROR in script
    assert '"work-project","science-project"' in script


def test_modular_work_owner_retires_work_project_context_mirror() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options="";["work-project","science-project"].forEach(id=>id)}'
            + _PROJECT_MIRROR
            + 'q("science-save").onclick=saveScienceRecord;'
        ).encode(),
        "text/javascript; charset=utf-8",
    )
    owned = patch_project_work_actions_module_response("/app.js", legacy)

    script = _finalize_context(owned)

    assert "WEB-PROJECT-WORK-ACTIONS-MODULE" in script
    assert _PROJECT_MIRROR not in script
    assert '"work-project","science-project"' not in script
    assert '"science-project"' in script
    assert 'q("science-save").onclick=saveScienceRecord;' in script
