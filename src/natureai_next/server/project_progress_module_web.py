"""Module-owned Project status and progress presentation for managed web.

The adapter mirrors the desktop workspace's project/task progress cues without
moving status semantics out of the authoritative Project services. It is a
read-only browser projection over governed Project and hierarchy APIs.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


_PROJECT_PROGRESS_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-PROGRESS-MODULE: Projects/Core status and progress presentation. */
(()=>{
 if(window.__fieldoraProjectProgressWired)return;window.__fieldoraProjectProgressWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:""};
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function emitError(error,fallback){
  const text=error?.message||fallback;
  const node=q("project-core-progress-message");if(node){node.textContent=text;node.classList.add("error")}
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}));
 }
 function ensureSurface(){
  const cockpit=q("project-desktop-cockpit");if(!cockpit)return false;
  let host=q("project-core-progress");
  if(!host){
   host=document.createElement("section");host.id="project-core-progress";host.className="card section";
   host.innerHTML='<div class="top"><div><h2>Project progress</h2><p class="muted">Status, completion, blocked work and schedule signals.</p></div><button id="project-core-progress-refresh" type="button">Refresh progress</button></div><div id="project-core-progress-body" class="project-stats"></div><p id="project-core-progress-message" class="status"></p>';
   cockpit.before(host);
  }
  return true;
 }
 function number(value){const parsed=Number(value);return Number.isFinite(parsed)?parsed:0}
 function taskProgress(task){
  if(Number.isFinite(Number(task.progress)))return Math.max(0,Math.min(100,Number(task.progress)));
  const category=String(task.status_category||task.status||"").toLowerCase();return category==="done"||category==="completed"?100:0;
 }
 function isBlocked(task){return task.blocked===true||String(task.status_category||task.status||"").toLowerCase()==="blocked"}
 function isDone(task){return taskProgress(task)>=100||["done","completed","closed"].includes(String(task.status_category||task.status||"").toLowerCase())}
 function overdue(task,today){const due=String(task.due_date||"");return Boolean(due&&!isDone(task)&&due<today)}
 function render(project,tasks){
  const host=q("project-core-progress-body");if(!host)return;
  if(!project){host.innerHTML='<div class="empty">Select a project to view progress.</div>';return}
  const today=new Date().toISOString().slice(0,10),total=tasks.length,done=tasks.filter(isDone).length,blocked=tasks.filter(isBlocked).length,late=tasks.filter(task=>overdue(task,today)).length;
  const progress=total?Math.round(tasks.reduce((sum,task)=>sum+taskProgress(task),0)/total):0;
  const milestones=tasks.filter(task=>task.milestone===true),milestonesDone=milestones.filter(isDone).length;
  const estimate=tasks.reduce((sum,task)=>sum+number(task.effective_estimate_hours||task.estimate_hours),0),realized=tasks.reduce((sum,task)=>sum+number(task.realized_hours||task.actual_hours),0);
  const schedule=[project.start_date||"—",project.due_date||"—"].join(" → ");
  host.innerHTML=`<div class="card"><strong>${esc(project.status||"active")}</strong><small class="muted">Project status</small></div><div class="card"><strong>${progress}%</strong><small class="muted">Average task progress</small></div><div class="card"><strong>${done}/${total}</strong><small class="muted">Tasks complete</small></div><div class="card"><strong>${blocked}</strong><small class="muted">Blocked tasks</small></div><div class="card"><strong>${late}</strong><small class="muted">Overdue tasks</small></div><div class="card"><strong>${milestonesDone}/${milestones.length}</strong><small class="muted">Milestones complete</small></div><div class="card"><strong>${esc(schedule)}</strong><small class="muted">Project schedule</small></div><div class="card"><strong>${realized.toFixed(1)} / ${estimate.toFixed(1)} h</strong><small class="muted">Realized / estimated effort</small></div>`;
  const message=q("project-core-progress-message");if(message){message.textContent="";message.classList.remove("error")}
 }
 async function refresh(){
  if(!ensureSurface())return;const pid=state.projectId||window.FieldoraProjects?.currentProject?.()||"";state.projectId=pid;
  if(!pid){render(null,[]);return}
  try{
   const encoded=encodeURIComponent(pid);
   const [projectResult,taskResult]=await Promise.all([api("/api/v1/projects",{purpose:"research"}),api(`/api/v1/tasks?project_id=${encoded}`,{purpose:"research"})]);
   const project=(projectResult.items||[]).find(item=>String(item.id)===String(pid))||null;render(project,taskResult.items||[]);
  }catch(error){render(null,[]);emitError(error,"Project progress could not be loaded.")}
 }
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  q("project-core-progress-refresh")?.addEventListener("click",refresh,{signal});state.projectId=window.FieldoraProjects?.currentProject?.()||"";refresh();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";refresh()});
 document.addEventListener("fieldora:project-work-changed",event=>{if(event.detail?.project_id===state.projectId)refresh()});
 document.addEventListener("fieldora:project-lifecycle-changed",event=>{if(event.detail?.project_id===state.projectId)refresh()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectProgress=Object.freeze({mount,unmount,refresh});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_progress_module_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Projects/Core progress presentation exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_PROGRESS_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_PROGRESS_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectProgressModuleWebApiMixin:
    """Compose the independently owned Project progress presentation."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_progress_module_response(target, response)
