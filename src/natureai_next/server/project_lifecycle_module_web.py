"""Module-owned Project lifecycle actions for Projects/Core.

The browser adapter owns selected-project edit, status and archive controls while
revision safety, PBAC, validation, audit and persistence remain in the existing
managed Project APIs.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_LIFECYCLE_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-LIFECYCLE-MODULE: Projects/Core lifecycle actions. */
(()=>{
 if(window.__fieldoraProjectLifecycleModuleWired)return;window.__fieldoraProjectLifecycleModuleWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",editingId:"",canEdit:false};
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 const projectList=()=>window.FieldoraModuleContracts?.resolve?.("projects.list.read")||null;
 const projectItems=()=>projectList()?.items?.()||[];
 const projectById=id=>projectItems().find(project=>String(project.id)===String(id))||null;
 function emitError(error,fallback){const text=error?.message||fallback;document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}))}
 function ensureSurface(){
  const page=q("page-projects");if(!page)return false;
  let button=q("project-core-edit-project");
  if(!button){button=document.createElement("button");button.id="project-core-edit-project";button.type="button";button.textContent="Edit selected project";button.dataset.fieldoraAuthorizationHidden="true";page.querySelector(".top")?.appendChild(button)}
  if(!q("project-core-lifecycle-editor")){
   const editor=document.createElement("section");editor.id="project-core-lifecycle-editor";editor.className="card section";editor.hidden=true;
   editor.innerHTML='<h2>Project lifecycle</h2><p id="project-core-lifecycle-revision" class="muted"></p><div class="form-grid"><label>Name<input id="project-core-lifecycle-name"></label><label>Status<select id="project-core-lifecycle-status"><option value="active">active</option><option value="cancelled">cancelled</option><option value="archived">archived</option></select></label><label>Start date<input id="project-core-lifecycle-start" type="date"></label><label>Due date<input id="project-core-lifecycle-due" type="date"></label><label>Budget<input id="project-core-lifecycle-budget" type="number" min="0" step="0.01"></label><label>Currency<input id="project-core-lifecycle-currency" maxlength="8"></label></div><label class="section">Description<textarea id="project-core-lifecycle-description"></textarea></label><div class="actions section"><button id="project-core-lifecycle-save" class="primary" type="button">Save details</button><button id="project-core-lifecycle-apply-status" type="button">Apply status</button><button id="project-core-lifecycle-archive" type="button">Archive project</button><button id="project-core-lifecycle-cancel" type="button">Close</button></div><p id="project-core-lifecycle-message" class="status"></p>';
   const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(editor);else page.appendChild(editor)
  }
  return true;
 }
 const button=()=>q("project-core-edit-project"),editor=()=>q("project-core-lifecycle-editor");
 function message(text,error=false){const node=q("project-core-lifecycle-message");if(node){node.textContent=text||"";node.classList.toggle("error",Boolean(error))}}
 function fill(project){
  if(!project)return;state.editingId=project.id;
  q("project-core-lifecycle-name").value=project.name||"";q("project-core-lifecycle-description").value=project.description||"";q("project-core-lifecycle-status").value=project.status||"active";q("project-core-lifecycle-start").value=project.start_date||"";q("project-core-lifecycle-due").value=project.due_date||"";q("project-core-lifecycle-budget").value=Number(project.budget||0);q("project-core-lifecycle-currency").value=project.currency||"EUR";q("project-core-lifecycle-revision").textContent=`Server revision ${project.revision}`;
 }
 async function refreshAuthority(){
  const control=button();if(control)control.dataset.fieldoraAuthorizationHidden="true";state.canEdit=false;if(!state.projectId)return false;
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});state.canEdit=caps?.actions?.edit===true;if(control)control.dataset.fieldoraAuthorizationHidden=state.canEdit?"false":"true";if(!state.canEdit&&editor())editor().hidden=true;return state.canEdit}catch(error){if(editor())editor().hidden=true;emitError(error,"Project permissions could not be loaded.");return false}
 }
 async function reloadProjects(focusId=state.editingId||state.projectId){
  const list=projectList();if(!list?.refresh)throw new Error("Project list contract is unavailable.");const items=await list.refresh();projects=Array.from(items||[],item=>({...item}));if(typeof projectOptions==="function")projectOptions();
  const context=projectContext();if(focusId&&context?.select)await context.select(focusId);
  return projectById(focusId);
 }
 async function conflict(){const current=await reloadProjects();if(current)fill(current);if(editor())editor().hidden=false;message("Project changed on the server. Latest values reloaded; review them before saving again.",true)}
 async function mutate(path,body,success){
  try{await api(path,{method:"PATCH",purpose:"research",body:JSON.stringify(body)});const current=await reloadProjects();if(current)fill(current);message(success);await refreshAuthority();document.dispatchEvent(new CustomEvent("fieldora:project-lifecycle-changed",{detail:{module_id:moduleId,project_id:state.editingId,item:current||null}}));return true}
  catch(error){if((error?.code||error?.message)==="revision_conflict"){await conflict();return false}message(error?.message||"Project update failed.",true);emitError(error,"Project update failed.");return false}
 }
 function open(){const project=projectById(state.projectId);if(!project||!state.canEdit)return;fill(project);message("");editor().hidden=false;q("project-core-lifecycle-name")?.focus()}
 async function save(){
  const project=projectById(state.editingId);if(!project)return;
  const name=q("project-core-lifecycle-name").value.trim();if(!name)return message("Project name is required.",true);
  const budget=Number(q("project-core-lifecycle-budget").value||0);if(!Number.isFinite(budget)||budget<0)return message("Budget must be zero or greater.",true);
  const start=q("project-core-lifecycle-start").value,due=q("project-core-lifecycle-due").value;if(start&&due&&due<start)return message("Due date must not be before start date.",true);
  await mutate(`/api/v1/projects/${encodeURIComponent(state.editingId)}`,{expected_revision:project.revision,name,description:q("project-core-lifecycle-description").value.trim(),start_date:start,due_date:due,budget,currency:q("project-core-lifecycle-currency").value.trim()||"EUR"},"Project details saved.")
 }
 async function applyStatus(){const project=projectById(state.editingId);if(!project)return;await mutate(`/api/v1/projects/${encodeURIComponent(state.editingId)}/status`,{expected_revision:project.revision,status:q("project-core-lifecycle-status").value},"Project status updated.")}
 async function archive(){const project=projectById(state.editingId);if(!project)return;const ok=await mutate(`/api/v1/projects/${encodeURIComponent(state.editingId)}/archive`,{expected_revision:project.revision},"Project archived.");if(ok&&editor())editor().hidden=true}
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  button()?.addEventListener("click",open,{signal});q("project-core-lifecycle-save")?.addEventListener("click",save,{signal});q("project-core-lifecycle-apply-status")?.addEventListener("click",applyStatus,{signal});q("project-core-lifecycle-archive")?.addEventListener("click",archive,{signal});q("project-core-lifecycle-cancel")?.addEventListener("click",()=>{editor().hidden=true;message("")},{signal});
  state.projectId=projectContext()?.current?.()||"";refreshAuthority();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;if(editor())editor().hidden=true}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";state.editingId="";refreshAuthority()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectLifecycle=Object.freeze({mount,unmount,open,refreshAuthority,currentProject:()=>state.projectId});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_lifecycle_module_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append module-owned Project lifecycle controls exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_LIFECYCLE_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_LIFECYCLE_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectLifecycleModuleWebApiMixin:
    """Compose Projects/Core lifecycle controls into the managed browser."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_lifecycle_module_response(target, response)
