from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_core_module_web import patch_project_core_module_response
from natureai_next.server.project_list_provider_web import patch_project_list_provider_response
from natureai_next.server.web_module_contract_runtime import (
    patch_runtime_contracts_response,
)


def _list_contract_runtime() -> ApiResponse:
    base = ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    shell = patch_modular_shell_response("/app.js", base)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    return patch_project_list_provider_response("/app.js", contracts)


def test_context_provider_requires_project_list_and_contract_runtime() -> None:
    plain = ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    assert patch_project_context_provider_response("/app.js", plain) is plain

    project = patch_project_core_module_response("/app.js", plain)
    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    assert patch_project_context_provider_response("/app.js", contracts) is contracts

    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    patched = patch_project_context_provider_response("/app.js", list_runtime)
    patched_again = patch_project_context_provider_response("/app.js", patched)

    assert patched.body == patched_again.body
    script = patched.body.decode("utf-8")
    assert script.count("WEB-PROJECT-CONTEXT-PROVIDER") == 1
    assert script.count("WEB-PROJECT-TOOLBAR-EXTENSION-PROVIDER") == 1
    assert 'contractName="projects.context.select"' in script
    assert 'toolbarContractName="projects.toolbar.extend"' in script
    assert "contracts.register(name,moduleId,value)" in script


def test_context_provider_owns_validated_project_selection_state() -> None:
    script = patch_project_context_provider_response(
        "/app.js", _list_contract_runtime()
    ).body.decode("utf-8")

    assert 'const state={projectId:""};' in script
    assert 'resolve?.("projects.list.read")' in script
    assert "const projectItems=()=>projectList()?.items?.()||[];" in script
    assert "if(requested&&!projectById(requested))return false;" in script
    assert "state.projectId=requested;publish();return true;" in script
    assert "current:()=>state.projectId" in script
    assert "fieldora:project-context-changed" in script
    assert "fieldora:project-list-changed" in script
    assert 'const fallback=String(projectItems()[0]?.id||"");' in script
    assert "window.FieldoraProjects" not in script
    assert "projects.selectProject(id)" not in script
    assert "owner()?.currentProject?.()" not in script


def test_context_provider_makes_managed_context_authoritative_for_legacy_work_save() -> None:
    legacy = ApiResponse(
        200,
        b'async function saveWorkItem(){const body={project_id:q("work-project").value,kind:q("work-kind").value};}',
        "text/javascript; charset=utf-8",
    )

    project = patch_project_core_module_response("/app.js", legacy)
    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    without_list = patch_project_context_provider_response("/app.js", contracts)
    assert without_list is contracts
    assert b'project_id:q("work-project").value,' in without_list.body

    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    patched = patch_project_context_provider_response("/app.js", list_runtime)
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.context.select")' in script
    assert 'const projectId=String(context.current?.()||"")' in script
    assert 'if(!projectId)throw new Error("Select a project before saving work.")' in script
    assert 'return q("work-project").value' in script
    assert 'project_id:q("work-project").value,' not in script
    assert 'q("work-project")' in script


def test_context_provider_uses_list_contract_for_legacy_project_presentation() -> None:
    legacy = ApiResponse(
        200,
        b'function openProject(id){const p=projects.find(x=>x.id===id);if(!p)return;render(p)}',
        "text/javascript; charset=utf-8",
    )

    project = patch_project_core_module_response("/app.js", legacy)
    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    patched = patch_project_context_provider_response("/app.js", list_runtime)
    script = patched.body.decode("utf-8")

    assert 'resolve?.("projects.list.read")' in script
    assert "Array.from(list.items()||[]).find(x=>x.id===id)" in script
    assert "const p=projects.find(x=>x.id===id);" not in script
    assert ":projects.find(" not in script


def test_context_provider_projects_legacy_selectors_without_ambient_list_mutation() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options=\'<option value="">Select project…</option>\'+'
            'projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("");'
            '["work-project","science-project"].forEach(id=>{if(q(id))q(id).innerHTML=options})}'
            'function syncLegacyProjectsFromListContract(){const list=window.FieldoraModuleContracts?.resolve?.('
            '"projects.list.read");if(!list?.items)return;projects=Array.from(list.items()||[],item=>({...item}));projectOptions();}'
            'document.addEventListener("fieldora:project-list-changed",syncLegacyProjectsFromListContract);'
        ).encode(),
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    script = patch_project_context_provider_response(
        "/app.js", list_runtime
    ).body.decode("utf-8")

    assert (
        '(window.FieldoraModuleContracts?.resolve?.("projects.list.read")?.items?.()||projects).map(p=>'
        in script
    )
    assert "projects=Array.from(list.items()||[],item=>({...item}))" not in script
    assert 'if(!list?.items)return;projectOptions();' in script
    assert '"work-project","science-project"' in script
    assert 'addEventListener("fieldora:project-list-changed",syncLegacyProjectsFromListContract)' in script


def test_context_provider_rewrites_projects_owned_initial_context_reads() -> None:
    legacy_read = b"window.FieldoraProjects?.currentProject?.()"
    legacy = ApiResponse(
        200,
        b";".join([b"const projectId=" + legacy_read + b'||""' for _ in range(4)]),
        "text/javascript; charset=utf-8",
    )
    shell = patch_modular_shell_response("/app.js", legacy)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    script = patch_project_context_provider_response(
        "/app.js", list_runtime
    ).body.decode("utf-8")

    managed = 'window.FieldoraModuleContracts?.resolve?.("projects.context.select")?.current?.()'
    assert "window.FieldoraProjects?.currentProject?.()" not in script
    assert script.count(managed) == 4


def test_context_provider_retires_projects_compatibility_facade() -> None:
    project = patch_project_core_module_response(
        "/app.js", ApiResponse(200, b"const base=true;", "text/javascript; charset=utf-8")
    )
    assert b"window.FieldoraProjects=Object.freeze" in project.body
    shell = patch_modular_shell_response("/app.js", project)
    contracts = patch_runtime_contracts_response("/app.js", shell)
    list_runtime = patch_project_list_provider_response("/app.js", contracts)
    script = patch_project_context_provider_response(
        "/app.js", list_runtime
    ).body.decode("utf-8")

    assert "window.FieldoraProjects=Object.freeze" not in script
    assert 'resolve?.("projects.context.select")' in script


def test_projects_toolbar_extension_provider_owns_cockpit_dom_boundary() -> None:
    script = patch_project_context_provider_response(
        "/app.js", _list_contract_runtime()
    ).body.decode("utf-8")

    assert 'querySelector(".cockpit-center .cockpit-toolbar")' in script
    assert "const toolbarImplementation=Object.freeze" in script
    assert "upsert:spec=>" in script
    assert "setEnabled:(key,enabled)=>" in script
    assert "remove:key=>" in script
    assert 'data-fieldora-extension-key' in script
    assert "fieldora:module-mount" in script
    assert "fieldora:module-unmount" in script
    assert "window.FieldoraProjectToolbar" not in script


def test_context_provider_exposes_contract_not_portfolio_navigation() -> None:
    script = patch_project_context_provider_response(
        "/app.js", _list_contract_runtime()
    ).body.decode("utf-8")

    assert "window.FieldoraProjectContext" not in script
    assert 'contractName="projects.context.select"' in script
    assert "window.openProject" not in script


def test_production_patch_composes_context_provider_after_list_and_runtime() -> None:
    legacy = ApiResponse(
        200,
        (
            'function projectOptions(){const options=\'<option value="">Select project…</option>\'+'
            'projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("");'
            '["work-project","science-project"].forEach(id=>{if(q(id))q(id).innerHTML=options})}'
        ).encode(),
        "text/javascript; charset=utf-8",
    )
    project = patch_project_core_module_response("/app.js", legacy)
    shell = patch_modular_shell_response("/app.js", project)
    final = patch_managed_web_response("/app.js", shell)
    script = final.body.decode("utf-8")

    assert script.count("WEB-MODULE-CONTRACT-RUNTIME") == 1
    assert script.count("WEB-PROJECT-LIST-PROVIDER") == 1
    assert script.count("WEB-PROJECT-CONTEXT-PROVIDER") == 1
    assert script.count("WEB-PROJECT-TOOLBAR-EXTENSION-PROVIDER") == 1
    assert "window.FieldoraProjects=Object.freeze" not in script
    assert "window.FieldoraProjectContext" not in script
    assert "projects=Array.from(list.items()||[],item=>({...item}))" not in script
    assert (
        '(window.FieldoraModuleContracts?.resolve?.("projects.list.read")?.items?.()||projects).map(p=>'
        in script
    )
    assert script.rfind("WEB-PROJECT-CONTEXT-PROVIDER") > script.rfind(
        "WEB-PROJECT-LIST-PROVIDER"
    )
    assert script.rfind("WEB-PROJECT-CONTEXT-PROVIDER") > script.rfind(
        "WEB-MODULE-CONTRACT-RUNTIME"
    )