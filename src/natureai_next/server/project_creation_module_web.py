"""Module-owned top-level Project creation for the managed Fieldora web client.

The browser owns only entry-point presentation, validation, refresh and feedback.
Authentication, create authorization, owner assignment and persistence remain in
the governed Project API.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_CREATION_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-CREATION-MODULE: Projects/Core top-level creation. */
(()=>{
 if(window.__fieldoraProjectCreationModuleWired)return;window.__fieldoraProjectCreationModuleWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null};
 function message(text,error=false){const node=q("project-core-create-message");if(node){node.textContent=text||"";node.classList.toggle("error",Boolean(error))}}
 function emitError(error,fallback){const text=error?.message||fallback;message(text,true);document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}))}
 function ensureSurface(){
  const page=q("page-projects"),top=page?.querySelector(".top");if(!page||!top)return false;
  let button=q("project-core-create");
  if(!button){button=document.createElement("button");button.id="project-core-create";button.className="primary";button.type="button";button.textContent="＋ Add project";top.appendChild(button)}
  if(!q("project-core-create-editor")){
   const editor=document.createElement("section");editor.id="project-core-create-editor";editor.className="card section";editor.hidden=true;
   editor.innerHTML='<h2>Add project</h2><div class="form-grid"><label>Name<input id="project-core-create-name" autocomplete="off"></label><label>Start date<input id="project-core-create-start" type="date"></label><label>Due date<input id="project-core-create-due" type="date"></label><label>Budget<input id="project-core-create-budget" type="number" min="0" step="0.01" value="0"></label><label>Currency<input id="project-core-create-currency" value="EUR" maxlength="8"></label></div><label class="section">Description<textarea id="project-core-create-description"></textarea></label><p class="muted">New projects start active. Ownership is assigned to the authenticated creator by the server.</p><div class="actions section"><button id="project-core-create-save" class="primary" type="button">Create project</button><button id="project-core-create-cancel" type="button">Cancel</button></div><p id="project-core-create-message" class="status"></p>';
   const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(editor);else page.appendChild(editor);
  }
  return true;
 }
 function openEditor(){const editor=q("project-core-create-editor");if(!editor)return;message("");editor.hidden=false;q("project-core-create-name")?.focus()}
 function closeEditor(){const editor=q("project-core-create-editor");if(editor)editor.hidden=true;message("")}
 async function reloadProjects(selectedId){
  const projectList=window.FieldoraModuleContracts?.resolve?.("projects.list.read");
  if(!projectList?.refresh)throw new Error("Project list contract is unavailable.");
  await projectList.refresh();
  const projectContext=window.FieldoraModuleContracts?.resolve?.("projects.context.select");
  if(selectedId&&projectContext?.select)await projectContext.select(selectedId);
  document.dispatchEvent(new CustomEvent("fieldora:projects-changed",{detail:{module_id:moduleId,project_id:selectedId||""}}));
 }
 async function save(){
  const name=q("project-core-create-name")?.value.trim()||"";if(!name)return message("Project name is required.",true);
  const start=q("project-core-create-start")?.value||"",due=q("project-core-create-due")?.value||"";
  if(start&&due&&due<start)return message("Project due date must not be before start date.",true);
  const budget=Number(q("project-core-create-budget")?.value||0);if(!Number.isFinite(budget)||budget<0)return message("Budget must be zero or greater.",true);
  const record={name,description:q("project-core-create-description")?.value.trim()||"",start_date:start,due_date:due,budget,currency:q("project-core-create-currency")?.value.trim()||"EUR"};
  try{
   message("Creating project…");
   const result=await api("/api/v1/projects",{method:"POST",purpose:"research",body:JSON.stringify(record)});
   const id=result?.item?.id||"";await reloadProjects(id);closeEditor();
   const status=q("project-core-module-status");if(status){status.textContent="Project created.";status.classList.remove("error")}
  }catch(error){emitError(error,"Project could not be created.")}
 }
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  q("project-core-create")?.addEventListener("click",openEditor,{signal});q("project-core-create-save")?.addEventListener("click",save,{signal});q("project-core-create-cancel")?.addEventListener("click",closeEditor,{signal});
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;closeEditor()}
 function handleCreateRequest(event){
  event?.preventDefault?.();
  const source=String(event?.detail?.source||"projects-create-request");
  const target=window.FieldoraModules?.navigate?.("/projects",source,"push");
  if(!target)return emitError(null,"Projects workspace is unavailable.");
  mount();openEditor();
 }
 document.addEventListener("fieldora:projects-create-requested",handleCreateRequest);
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectCreation=Object.freeze({mount,unmount,openEditor});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_creation_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the independently owned Project creation adapter once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_CREATION_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_CREATION_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectCreationModuleWebApiMixin:
    """Compose Projects/Core top-level creation controls into the browser."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_creation_module_response(target, response)
