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


def _patch_legacy_work_project_context(body: bytes) -> bytes:
    """Make managed Project context authoritative without removing the legacy editor."""

    return body.replace(_LEGACY_WORK_PROJECT_ID, _MANAGED_WORK_PROJECT_ID, 1)


def _patch_legacy_project_presentation_list(body: bytes) -> bytes:
    """Read managed Project presentation records from the canonical list contract."""

    return body.replace(_LEGACY_OPEN_PROJECT_LOOKUP, _MANAGED_OPEN_PROJECT_LOOKUP, 1)


def _patch_projects_owned_context_reads(body: bytes) -> bytes:
    """Route composed Projects adapters through the canonical context contract."""

    return body.replace(_LEGACY_PROJECT_CONTEXT_READ, _MANAGED_PROJECT_CONTEXT_READ)


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
 window.FieldoraProjectContext=implementation;
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
    context = ApiResponse(
        selected.status,
        body + _PROJECT_CONTEXT_PROVIDER_PATCH,
        selected.content_type,
        selected.headers,
    )
    return patch_project_inspector_module_response(target, context)
