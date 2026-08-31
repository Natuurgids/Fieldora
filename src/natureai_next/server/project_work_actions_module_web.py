"""Module-owned create actions for the Projects/Core work hierarchy.

The adapter owns visible creation controls and validation for phases, tasks,
milestones, subtasks, sprints and allocations. Persistence and authorization stay
in the managed Project hierarchy API; capability projection only controls browser
discoverability and is never treated as authorization.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


_PROJECT_WORK_ACTIONS_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-WORK-ACTIONS-MODULE: Projects/Core creation actions. */
(()=>{
 if(window.__fieldoraProjectWorkActionsWired)return;window.__fieldoraProjectWorkActionsWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",selectedWork:{kind:"project",id:""},canEdit:false};
 const escWork=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function emitError(error,fallback){
  const message=error?.message||fallback;
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(message)}}));
 }
 function ensureSurface(){
  const cockpit=q("project-desktop-cockpit"),toolbar=cockpit?.querySelector(".cockpit-center .cockpit-toolbar");if(!cockpit||!toolbar)return false;
  let actions=q("project-core-work-actions");
  if(!actions){
   actions=document.createElement("div");actions.id="project-core-work-actions";actions.className="actions";actions.dataset.fieldoraAuthorizationHidden="true";
   actions.innerHTML='<button type="button" data-project-work-create="phase">New phase</button><button type="button" data-project-work-create="task">New task</button><button type="button" data-project-work-create="milestone">New milestone</button><button type="button" data-project-work-create="subtask" hidden>New subtask</button><button type="button" data-project-work-create="sprint">New sprint</button><button type="button" data-project-work-create="allocation">New allocation</button>';
   toolbar.prepend(actions);
  }
  if(!q("project-core-work-editor")){
   const editor=document.createElement("section");editor.id="project-core-work-editor";editor.className="card section";editor.hidden=true;cockpit.before(editor);
  }
  return true;
 }
 function actions(){return q("project-core-work-actions")}
 function editor(){return q("project-core-work-editor")}
 function setSelection(kind,id){
  state.selectedWork={kind:kind||"project",id:id||state.projectId||""};
  const sub=actions()?.querySelector('[data-project-work-create="subtask"]');if(sub)sub.hidden=state.selectedWork.kind!=="task";
 }
 async function refreshAuthority(){
  const host=actions();if(host)host.dataset.fieldoraAuthorizationHidden="true";state.canEdit=false;
  if(!state.projectId)return;
  try{
   const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});
   state.canEdit=caps?.actions?.edit===true;if(host)host.dataset.fieldoraAuthorizationHidden=state.canEdit?"false":"true";
  }catch(error){if(host)host.dataset.fieldoraAuthorizationHidden="true";emitError(error,"Project permissions could not be loaded.")}
 }
 function relationship(kind){
  if(kind==="subtask")return `Parent task: ${state.selectedWork.id}`;
  if((kind==="task"||kind==="milestone"||kind==="allocation")&&state.selectedWork.kind==="phase")return `Phase: ${state.selectedWork.id}`;
  return `Project: ${state.projectId}`;
 }
 function label(kind){return ({phase:"phase",task:"task",milestone:"milestone",subtask:"subtask",sprint:"sprint",allocation:"allocation"})[kind]||kind}
 function openEditor(kind){
  if(!state.projectId||!state.canEdit)return;
  if(kind==="subtask"&&state.selectedWork.kind!=="task")return;
  const host=editor();if(!host)return;
  let fields="";
  if(kind==="phase")fields='<label>Name<input id="project-core-child-name" autocomplete="off"></label><label>Description<textarea id="project-core-child-description"></textarea></label>';
  if(kind==="task"||kind==="milestone"||kind==="subtask")fields='<label>Title<input id="project-core-child-title" autocomplete="off"></label><label>Description<textarea id="project-core-child-description"></textarea></label><label>Owner<input id="project-core-child-owner" autocomplete="off"></label><label>Due date<input id="project-core-child-due" type="date"></label>';
  if(kind==="sprint")fields='<label>Name<input id="project-core-child-name" autocomplete="off"></label><label>Start date<input id="project-core-child-start" type="date"></label><label>End date<input id="project-core-child-end" type="date"></label><label>Goal<textarea id="project-core-child-goal"></textarea></label>';
  if(kind==="allocation")fields='<label>User<input id="project-core-child-user" autocomplete="off"></label><label>Start date<input id="project-core-child-start" type="date"></label><label>End date<input id="project-core-child-end" type="date"></label><label>Hours / week<input id="project-core-child-hours" type="number" min="0" step="0.25" value="0"></label><label>Allocation %<input id="project-core-child-percent" type="number" min="0" max="100" step="1" value="0"></label><label>Role<input id="project-core-child-role" autocomplete="off"></label>';
  host.dataset.kind=kind;host.innerHTML=`<h2>New ${escWork(label(kind))}</h2><p class="muted">${escWork(relationship(kind))}</p><div class="form-grid">${fields}</div><div class="actions section"><button id="project-core-child-save" class="primary" type="button">Create ${escWork(label(kind))}</button><button id="project-core-child-cancel" type="button">Cancel</button></div><p id="project-core-child-message" class="status"></p>`;host.hidden=false;
  q("project-core-child-cancel").onclick=()=>{host.hidden=true};q("project-core-child-save").onclick=saveChild;host.querySelector("input")?.focus();
 }
 function fail(message){const node=q("project-core-child-message");if(node){node.textContent=message;node.classList.add("error")}return false}
 async function saveChild(){
  const host=editor(),kind=host?.dataset.kind;if(!host||!kind||!state.projectId)return;
  let path="",record={project_id:state.projectId};
  if(kind==="phase"){
   record.name=q("project-core-child-name").value.trim();record.description=q("project-core-child-description").value.trim();path="/api/v1/phases";if(!record.name)return fail("Phase name is required.");
  }else if(kind==="task"||kind==="milestone"||kind==="subtask"){
   record.title=q("project-core-child-title").value.trim();record.description=q("project-core-child-description").value.trim();record.owner_id=q("project-core-child-owner").value.trim();record.due_date=q("project-core-child-due").value;path="/api/v1/tasks";if(!record.title)return fail("Task title is required.");
   if(kind==="milestone")record.milestone=true;
   if(kind==="subtask")record.parent_task_id=state.selectedWork.id;else if(state.selectedWork.kind==="phase")record.phase_id=state.selectedWork.id;
  }else if(kind==="sprint"){
   record.name=q("project-core-child-name").value.trim();record.start_date=q("project-core-child-start").value;record.end_date=q("project-core-child-end").value;record.goal=q("project-core-child-goal").value.trim();path="/api/v1/sprints";if(!record.name)return fail("Sprint name is required.");
   if(record.start_date&&record.end_date&&record.end_date<record.start_date)return fail("Sprint end date must not be before start date.");
  }else if(kind==="allocation"){
   record.user_id=q("project-core-child-user").value.trim();record.start_date=q("project-core-child-start").value;record.end_date=q("project-core-child-end").value;record.hours_per_week=Number(q("project-core-child-hours").value||0);record.allocation_percent=Number(q("project-core-child-percent").value||0);record.role=q("project-core-child-role").value.trim();if(state.selectedWork.kind==="phase")record.phase_id=state.selectedWork.id;path="/api/v1/allocations";
   if(!record.user_id||!record.start_date)return fail("User and start date are required.");if(!Number.isFinite(record.hours_per_week)||record.hours_per_week<0)return fail("Hours per week must be zero or greater.");if(!Number.isFinite(record.allocation_percent)||record.allocation_percent<0||record.allocation_percent>100)return fail("Allocation must be between 0 and 100 percent.");if(record.end_date&&record.end_date<record.start_date)return fail("Allocation end date must not be before start date.");
  }
  try{
   const result=await api(path,{method:"POST",purpose:"research",body:JSON.stringify(record)});host.hidden=true;
   document.dispatchEvent(new CustomEvent("fieldora:project-work-changed",{detail:{module_id:moduleId,project_id:state.projectId,kind,item:result?.item||null}}));
  }catch(error){fail(error?.message||"Project work item could not be created.");emitError(error,"Project work item could not be created.")}
 }
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  actions()?.addEventListener("click",event=>{const button=event.target.closest?.("[data-project-work-create]");if(button)openEditor(button.dataset.projectWorkCreate)},{signal});
  q("project-desktop-cockpit")?.addEventListener("click",event=>{const row=event.target.closest?.("[data-project-work-kind]");if(row)setSelection(row.dataset.projectWorkKind,row.dataset.projectWorkId)},{signal});
  state.projectId=window.FieldoraProjects?.currentProject?.()||"";setSelection("project",state.projectId);refreshAuthority();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;const host=editor();if(host)host.hidden=true}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";setSelection("project",state.projectId);refreshAuthority()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectWorkActions=Object.freeze({mount,unmount,refreshAuthority,openEditor,currentSelection:()=>({...state.selectedWork})});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_work_actions_module_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append module-owned Project work actions exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_WORK_ACTIONS_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_WORK_ACTIONS_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectWorkActionsModuleWebApiMixin:
    """Compose Projects/Core work creation controls into the managed browser."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_work_actions_module_response(target, response)
