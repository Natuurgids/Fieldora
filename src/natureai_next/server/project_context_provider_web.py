"""Projects-owned browser providers for project context and cockpit extensions."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_inspector_module_web import (
    patch_project_inspector_module_response,
)
from natureai_next.server.project_selected_record_provider_web import (
    patch_project_selected_record_provider_response,
)

_LEGACY_WORK_PROJECT_ID = b'project_id:q("work-project").value,'
_MANAGED_WORK_PROJECT_ID = (
    b'project_id:(()=>{const context=window.FieldoraModuleContracts?.resolve?.('
    b'"projects.context.select");if(context){const projectId=String(context.current?.()||"");'
    b'if(!projectId)throw new Error("Select a project before saving work.");return projectId}'
    b'return q("work-project").value})(),'
)
_LEGACY_OPEN_PROJECT_LOOKUP = b"const p=projects.find(x=>x.id===id);"
_MANAGED_OPEN_PROJECT_LOOKUP = (
    b'const list=window.FieldoraModuleContracts?.resolve?.("projects.list.read"),'
    b'p=list?.items?Array.from(list.items()||[]).find(x=>x.id===id):null;'
)
_LEGACY_PROJECT_CONTEXT_READ = b"window.FieldoraProjects?.currentProject?.()"
_MANAGED_PROJECT_CONTEXT_READ = (
    b'window.FieldoraModuleContracts?.resolve?.("projects.context.select")?.current?.()'
)
_LEGACY_COCKPIT_PROJECT_CONTEXT_WRITE = (
    b'cockpitProjectId=id||"";selectedProject=cockpitProjectId;'
)
_MANAGED_COCKPIT_PROJECT_CONTEXT_WRITE = (
    b'cockpitProjectId=id||"";const context=window.FieldoraModuleContracts?.resolve?.('
    b'"projects.context.select");if(!context?.select?.(cockpitProjectId))return;'
)
_MANAGED_PROJECT_CONTEXT_CURRENT = (
    b'window.FieldoraModuleContracts?.resolve?.("projects.context.select")?.current?.()||""'
)
_LEGACY_PROJECT_RUNTIME_CONTEXT_READS = (
    (b'const id=selectedProject||"";', b'const id=' + _MANAGED_PROJECT_CONTEXT_CURRENT + b';'),
    (b',id=selectedProject||"";', b',id=' + _MANAGED_PROJECT_CONTEXT_CURRENT + b';'),
    (
        b'const projectId=selectedProject||"",title=',
        b'const projectId=' + _MANAGED_PROJECT_CONTEXT_CURRENT + b',title=',
    ),
    (
        b'const projectId=selectedProject||"",mediaId=',
        b'const projectId=' + _MANAGED_PROJECT_CONTEXT_CURRENT + b',mediaId=',
    ),
)
_LEGACY_PROJECT_OPTIONS_SOURCE = (
    'function projectOptions(){const options=\'<option value="">Select project…</option>\'+'
    'projects.map(p=>'
).encode()
_MANAGED_PROJECT_OPTIONS_SOURCE = (
    'function projectOptions(){const options=\'<option value="">Select project…</option>\'+'
    '(window.FieldoraModuleContracts?.resolve?.("projects.list.read")?.items?.()||projects).map(p=>'
).encode()
_LEGACY_PROJECT_LIST_MIRROR = (
    b'projects=Array.from(list.items()||[],item=>({...item}));projectOptions();'
)
_MANAGED_PROJECT_SELECTOR_REFRESH = b"projectOptions();"
_PROJECTS_COMPATIBILITY_FACADE = (
    b'window.FieldoraProjects=Object.freeze({mount,unmount,selectProject:id=>projectContext()?.select?.(id)??false,'
    b'setCenter,refreshWork:loadWork,refreshEvidence:loadEvidence,currentProject:()=>String(projectContext()?.current?.()||""),'
    b'currentView:()=>state.centerView});'
)
_PROJECT_WORK_ACTIONS_OWNER_MARKER = b"WEB-PROJECT-WORK-ACTIONS-MODULE"
_LEGACY_WORK_EDITOR_START = b"async function saveWorkItem(){"
_LEGACY_WORK_EDITOR_END = b"async function loadCapacity(){"
_LEGACY_WORK_SAVE_WIRING = b'q("work-save").onclick=saveWorkItem;'
_LEGACY_WORK_PROJECT_OPTIONS = b'"work-project","science-project"'
_MANAGED_WORK_PROJECT_OPTIONS = b'"science-project"'
_PROJECT_CORE_WORK_PROJECT_MIRROR = (
    b'if(q("work-project"))q("work-project").value=state.projectId;'
)


def _patch_legacy_work_project_context(body: bytes) -> bytes:
    """Make managed Project context authoritative without removing the legacy editor."""

    return body.replace(_LEGACY_WORK_PROJECT_ID, _MANAGED_WORK_PROJECT_ID, 1)


def _patch_legacy_project_presentation_list(body: bytes) -> bytes:
    """Read managed Project presentation records from the canonical list contract."""

    return body.replace(_LEGACY_OPEN_PROJECT_LOOKUP, _MANAGED_OPEN_PROJECT_LOOKUP, 1)


def _patch_projects_owned_context_reads(body: bytes) -> bytes:
    """Route composed Projects adapters through the canonical context contract."""

    return body.replace(_LEGACY_PROJECT_CONTEXT_READ, _MANAGED_PROJECT_CONTEXT_READ)


def _patch_private_project_context_consumers(body: bytes) -> bytes:
    """Remove cross-module reads and writes of the shell-private selectedProject state."""

    body = body.replace(
        _LEGACY_COCKPIT_PROJECT_CONTEXT_WRITE,
        _MANAGED_COCKPIT_PROJECT_CONTEXT_WRITE,
        1,
    )
    for legacy, managed in _LEGACY_PROJECT_RUNTIME_CONTEXT_READS:
        body = body.replace(legacy, managed, 1)
    return body


def _patch_legacy_project_selector_source(body: bytes) -> bytes:
    """Project legacy selectors from the list contract without mutating ambient state."""

    body = body.replace(
        _LEGACY_PROJECT_OPTIONS_SOURCE, _MANAGED_PROJECT_OPTIONS_SOURCE, 1
    )
    return body.replace(
        _LEGACY_PROJECT_LIST_MIRROR, _MANAGED_PROJECT_SELECTOR_REFRESH, 1
    )


def _strip_legacy_range(body: bytes, start: bytes, end: bytes) -> bytes:
    start_index = body.find(start)
    if start_index < 0:
        return body
    end_index = body.find(end, start_index)
    if end_index < 0:
        return body
    return body[:start_index] + body[end_index:]


def _retire_legacy_work_editor(body: bytes) -> bytes:
    """Retire the legacy Project work editor once its modular owner is present."""

    if _PROJECT_WORK_ACTIONS_OWNER_MARKER not in body:
        return body
    body = _strip_legacy_range(body, _LEGACY_WORK_EDITOR_START, _LEGACY_WORK_EDITOR_END)
    body = body.replace(_LEGACY_WORK_SAVE_WIRING, b"", 1)
    body = body.replace(_PROJECT_CORE_WORK_PROJECT_MIRROR, b"", 1)
    return body.replace(_LEGACY_WORK_PROJECT_OPTIONS, _MANAGED_WORK_PROJECT_OPTIONS, 1)


def _retire_projects_compatibility_facade(body: bytes) -> bytes:
    """Remove the obsolete ambient Projects integration façade from final app.js."""

    return body.replace(_PROJECTS_COMPATIBILITY_FACADE, b"", 1)


_PROJECT_CONTEXT_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-CONTEXT-PROVIDER: Projects-owned context selection contract. */
/* WEB-PROJECT-TOOLBAR-EXTENSION-PROVIDER: Projects-owned cockpit action contract. */
(()=>{
 if(window.__fieldoraProjectContextProviderWired)return;window.__fieldoraProjectContextProviderWired=true;
 const moduleId="projects.core",contractName="projects.context.select",toolbarContractName="projects.toolbar.extend";
 const state={projectId:""};
 const projectList=()=>window.FieldoraModuleContracts?.resolve?.("projects.list.read")||null;
 const projectItems=()=>projectList()?.items?.()||[];
 const projectById=id=>projectItems().find(project=>String(project.id)===String(id))||null;
 function publish(){document.dispatchEvent(new CustomEvent("fieldora:project-context-changed",{detail:{module_id:moduleId,project_id:state.projectId}}))}
 function select(id){
  const requested=String(id||"");
  if(requested&&!projectById(requested))return false;
  if(state.projectId===requested)return true;
  state.projectId=requested;publish();return true;
 }
 function reconcile(){
  if(state.projectId&&projectById(state.projectId))return state.projectId;
  const fallback=String(projectItems()[0]?.id||"");
  if(fallback!==state.projectId){state.projectId=fallback;publish()}
  return state.projectId;
 }
 const implementation=Object.freeze({select,current:()=>state.projectId});
 const toolbarEntries=new Map();
 const toolbar=()=>document.getElementById("project-desktop-cockpit")?.querySelector(".cockpit-center .cockpit-toolbar")||null;
 function toolbarButton(key){const host=toolbar();if(!host)return null;return Array.from(host.querySelectorAll("[data-fieldora-extension-key]")).find(button=>button.dataset.fieldoraExtensionKey===key)||null}
 function renderToolbarEntry(key){
  const entry=toolbarEntries.get(key),host=toolbar();if(!entry||!host)return false;
  let button=toolbarButton(key);
  if(!button){button=document.createElement("button");button.type="button";button.dataset.fieldoraExtensionKey=key;button.addEventListener("click",()=>toolbarEntries.get(key)?.activate?.());host.appendChild(button)}
  button.textContent=entry.label;button.dataset.fieldoraOwnerModule=entry.ownerModule;button.dataset.fieldoraAction=entry.action;button.disabled=!entry.enabled;return true;
 }
 function renderToolbar(){toolbarEntries.forEach((_,key)=>renderToolbarEntry(key))}
 function clearToolbar(){toolbarEntries.forEach((_,key)=>toolbarButton(key)?.remove())}
 const toolbarImplementation=Object.freeze({
  upsert:spec=>{
   const key=String(spec?.key||"").trim(),label=String(spec?.label||"").trim(),ownerModule=String(spec?.ownerModule||"").trim(),action=String(spec?.action||"").trim();
   if(!key||!label||!ownerModule||!action||typeof spec?.activate!=="function")throw new Error("Projects toolbar extension requires key, label, ownerModule, action and activate.");
   toolbarEntries.set(key,Object.freeze({key,label,ownerModule,action,enabled:spec.enabled!==false,activate:spec.activate}));renderToolbarEntry(key);return key;
  },
  setEnabled:(key,enabled)=>{const token=String(key||"").trim(),entry=toolbarEntries.get(token);if(!entry)return false;toolbarEntries.set(token,Object.freeze({...entry,enabled:Boolean(enabled)}));renderToolbarEntry(token);return true},
  remove:key=>{const token=String(key||"").trim(),removed=toolbarEntries.delete(token);toolbarButton(token)?.remove();return removed}
 });
 function registerContract(name,value){
  const contracts=window.FieldoraModuleContracts;if(!contracts||contracts.provider?.(name)!==moduleId)return false;
  const current=contracts.resolve(name);if(current)return current===value;
  contracts.register(name,moduleId,value);return true;
 }
 function register(){return registerContract(contractName,implementation)}
 function registerToolbar(){return registerContract(toolbarContractName,toolbarImplementation)}
 register();registerToolbar();reconcile();
 document.addEventListener('fieldora:contracts-ready',()=>{register();registerToolbar();reconcile()},{once:true});
 document.addEventListener('fieldora:project-list-changed',reconcile);
 document.addEventListener('fieldora:module-mount',event=>{if(event.detail?.module?.module_id===moduleId)renderToolbar()});
 document.addEventListener('fieldora:module-unmount',event=>{if(event.detail?.module?.module_id===moduleId)clearToolbar()});
})();
""",
    "utf-8",
)


def patch_project_context_provider_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append selected-record, context, toolbar and replaceable inspector providers."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-PROJECT-LIST-PROVIDER" not in response.body
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _PROJECT_CONTEXT_PROVIDER_PATCH in response.body
    ):
        return response
    selected = patch_project_selected_record_provider_response(target, response)
    body = _patch_legacy_work_project_context(selected.body)
    body = _patch_legacy_project_presentation_list(body)
    body = _patch_projects_owned_context_reads(body)
    body = _patch_private_project_context_consumers(body)
    body = _patch_legacy_project_selector_source(body)
    body = _retire_legacy_work_editor(body)
    body = _retire_projects_compatibility_facade(body)
    context = ApiResponse(
        selected.status,
        body + _PROJECT_CONTEXT_PROVIDER_PATCH,
        selected.content_type,
        selected.headers,
    )
    return patch_project_inspector_module_response(target, context)
