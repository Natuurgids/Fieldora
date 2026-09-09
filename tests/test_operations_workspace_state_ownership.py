from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.web_module_contract_runtime import patch_runtime_contracts_response


def test_operations_workspace_owner_rebinds_legacy_state_controls() -> None:
    legacy = ApiResponse(
        200,
        (
            b'let operationsDomain="assets";'
            b'async function loadOperations(){}'
            b'document.querySelectorAll("[data-operations-domain]").forEach('
            b'b=>b.onclick=()=>{operationsDomain=b.dataset.operationsDomain;loadOperations()});'
            b'document.getElementById("operations-refresh").onclick=loadOperations;'
        ),
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    script = patch_runtime_contracts_response("/app.js", shell).body.decode("utf-8")
    runtime = script.split("WEB-MODULE-CONTRACT-RUNTIME", 1)[1]

    assert "const implementation=Object.freeze({currentDomain,records:currentRecords" in runtime
    assert "register('operations.workspace.host','application.operations-workspace',implementation)" in runtime
    assert "refreshButton.onclick=()=>implementation.refresh()" in runtime
    assert "implementation.selectDomain(button.dataset.operationsDomain)" in runtime
    assert runtime.index("refreshButton.onclick=()=>implementation.refresh()") > runtime.index(
        "register('operations.workspace.host','application.operations-workspace',implementation)"
    )
    assert runtime.index("implementation.selectDomain(button.dataset.operationsDomain)") > runtime.index(
        "register('operations.workspace.host','application.operations-workspace',implementation)"
    )


def test_operations_workspace_state_owner_keeps_snapshot_publication_inside_host() -> None:
    legacy = ApiResponse(
        200,
        b'let operationsDomain="assets";async function loadOperations(){}',
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    runtime = patch_runtime_contracts_response("/app.js", shell).body.decode("utf-8")

    assert "operationsWorkspaceRecords=captureRecords()" in runtime
    assert "const snapshot=Object.freeze({domain:currentDomain(),records:operationsWorkspaceRecords})" in runtime
    assert "records:currentRecords" in runtime
    assert "const selectDomain=async domain=>" in runtime


def test_operations_workspace_domain_is_private_owner_state() -> None:
    legacy = ApiResponse(
        200,
        b'let operationsDomain="assets";async function loadOperations(){}',
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    runtime = patch_runtime_contracts_response("/app.js", shell).body.decode("utf-8")

    assert (
        "let operationsWorkspaceDomain=typeof operationsDomain==='undefined'?null:String(operationsDomain)"
        in runtime
    )
    assert "const currentDomain=()=>operationsWorkspaceDomain" in runtime
    assert (
        "operationsDomain=operationsWorkspaceDomain;const result=await baseOperationsLoad()"
        in runtime
    )
    assert "operationsWorkspaceDomain=next;return loadOperations()" in runtime
    assert "currentDomain=()=>typeof operationsDomain" not in runtime
    assert "operationsDomain=next" not in runtime
