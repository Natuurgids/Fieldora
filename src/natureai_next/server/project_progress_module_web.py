"""Module-owned Project progress and planning views for managed web.

The adapter mirrors the desktop workspace's project/task progress cues, editable
Kanban status movement, and date-driven Gantt view without moving workflow
semantics out of the authoritative Project services.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_PROGRESS_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-PROGRESS-MODULE: Projects/Core status, Kanban and Gantt planning. */
(()=>{
 if(window.__fieldoraProjectProgressWired)return;window.__fieldoraProjectProgressWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",view:"overview",canEdit:false,project:null,tasks:[],statuses:[]};
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
   host.innerHTML='<div class="top"><div><h2>Project planning</h2><p class="muted">Progress overview, workflow board and date-driven timeline.</p></div><button id="project-core-progress-refresh" type="button">Refresh planning</button></div><div class="tabs" role="tablist" aria-label="Project planning views"><button type="button" data-project-planning-view="overview" aria-selected="true">Overview</button><button type="button" data-project-planning-view="kanban">Kanban</button><button type="button" data-project-planning-view="gantt">Gantt</button></div><div id="project-core-progress-body"></div><p id="project-core-progress-message" class="status"></p>';
   cockpit.before(host);
  }
  return true;
 }
 function number(value){const parsed=Number(value);return Number.isFinite(parsed)?parsed:0}
 function taskProgress(task){
  if(task.progress!==null&&task.progress!==undefined&&task.progress!==""&&Number.isFinite(Number(task.progress)))return Math.max(0,Math.min(100,Number(task.progress)));
  const category=String(task.status_category||task.status||"").toLowerCase();return category==="done"||category==="completed"?100:0;
 }
 function isBlocked(task){return task.blocked===true||String(task.status_category||task.status||"").toLowerCase()==="blocked"}
 function isDone(task){return taskProgress(task)>=100||["done","completed","closed"].includes(String(task.status_category||task.status||"").toLowerCase())}
 function overdue(task,today){const due=String(task.due_date||"");return Boolean(due&&!isDone(task)&&due<today)}
 function localIsoDate(){const now=new Date(),year=now.getFullYear(),month=String(now.getMonth()+1).padStart(2,"0"),day=String(now.getDate()).padStart(2,"0");return `${year}-${month}-${day}`}
 function statusMatches(task,status){return String(task.status_id||"")===String(status.status_id||status.id||"")||String(task.status_name||task.status||"")===String(status.name||"")}
 function renderOverview(){
  const host=q("project-core-progress-body"),project=state.project,tasks=state.tasks;if(!host)return;
  if(!project){host.innerHTML='<div class="empty">Select a project to view progress.</div>';return}
  const today=localIsoDate(),total=tasks.length,done=tasks.filter(isDone).length,blocked=tasks.filter(isBlocked).length,late=tasks.filter(task=>overdue(task,today)).length;
  const progress=total?Math.round(tasks.reduce((sum,task)=>sum+taskProgress(task),0)/total):0;
  const milestones=tasks.filter(task=>task.milestone===true),milestonesDone=milestones.filter(isDone).length;
  const estimate=tasks.reduce((sum,task)=>sum+number(task.effective_estimate_hours??task.estimate_hours??task.manual_estimate),0),realized=tasks.reduce((sum,task)=>sum+number(task.realized_hours??task.realized??task.actual_hours),0);
  const schedule=[project.start_date||"—",project.due_date||"—"].join(" → ");
  host.innerHTML=`<div class="project-stats"><div class="card"><strong>${esc(project.status||"active")}</strong><small class="muted">Project status</small></div><div class="card"><strong>${progress}%</strong><small class="muted">Average task progress</small></div><div class="card"><strong>${done}/${total}</strong><small class="muted">Tasks complete</small></div><div class="card"><strong>${blocked}</strong><small class="muted">Blocked tasks</small></div><div class="card"><strong>${late}</strong><small class="muted">Overdue tasks</small></div><div class="card"><strong>${milestonesDone}/${milestones.length}</strong><small class="muted">Milestones complete</small></div><div class="card"><strong>${esc(schedule)}</strong><small class="muted">Project schedule</small></div><div class="card"><strong>${realized.toFixed(1)} / ${estimate.toFixed(1)} h</strong><small class="muted">Realized / estimated effort</small></div></div>`;
 }
 function statusOptions(task){return state.statuses.map(status=>{const id=String(status.status_id||status.id||"");return `<option value="${esc(id)}" ${statusMatches(task,status)?"selected":""}>${esc(status.name||id)}</option>`}).join("")}
 function renderKanban(){
  const host=q("project-core-progress-body");if(!host)return;
  if(!state.project){host.innerHTML='<div class="empty">Select a project to view its Kanban board.</div>';return}
  if(!state.statuses.length){host.innerHTML='<div class="empty">This project has no workflow statuses.</div>';return}
  host.innerHTML=`<div class="project-kanban" style="display:grid;grid-auto-flow:column;grid-auto-columns:minmax(230px,1fr);gap:12px;overflow:auto;padding-bottom:6px">${state.statuses.map(status=>{const id=String(status.status_id||status.id||""),items=state.tasks.filter(task=>statusMatches(task,status));return `<section class="card" data-project-kanban-column="${esc(id)}"><div class="top"><strong>${esc(status.name||id)}</strong><span class="muted">${items.length}</span></div><div data-project-kanban-drop="${esc(id)}" style="min-height:240px">${items.map(task=>`<article class="card section" draggable="${state.canEdit}" data-project-kanban-task="${esc(task.id)}"><button type="button" class="link" data-project-planning-task="${esc(task.id)}"><strong>${esc(task.title||task.name||task.id)}</strong></button><p class="muted">${esc(task.assignee_id||task.owner_id||"Unassigned")} · ${taskProgress(task)}%</p>${state.canEdit?`<label class="muted">Status<select data-project-kanban-status="${esc(task.id)}">${statusOptions(task)}</select></label>`:""}</article>`).join("")||'<div class="empty">No tasks.</div>'}</div></section>`}).join("")}</div>`;
 }
 function ganttRange(){
  const rows=state.tasks.map(task=>{const start=String(task.start_date||task.due_date||""),end=String(task.due_date||task.start_date||"");if(!start||!end)return null;const a=Date.parse(`${start}T00:00:00Z`),b=Date.parse(`${end}T00:00:00Z`);if(!Number.isFinite(a)||!Number.isFinite(b))return null;return {task,start:a,end:Math.max(a,b)}}).filter(Boolean);
  if(!rows.length)return {rows:[],min:0,max:0,span:1};const min=Math.min(...rows.map(row=>row.start)),max=Math.max(...rows.map(row=>row.end)),day=86400000;return {rows,min,max,span:Math.max(day,max-min+day)};
 }
 function renderGantt(){
  const host=q("project-core-progress-body");if(!host)return;
  if(!state.project){host.innerHTML='<div class="empty">Select a project to view its Gantt timeline.</div>';return}
  const range=ganttRange();if(!range.rows.length){host.innerHTML='<div class="empty">Add task dates to build the Gantt timeline.</div>';return}
  const fmt=value=>new Date(value).toISOString().slice(0,10);
  host.innerHTML=`<div class="card section"><div class="top"><strong>${fmt(range.min)}</strong><strong>${fmt(range.max)}</strong></div><div>${range.rows.map(row=>{const left=((row.start-range.min)/range.span)*100,width=Math.max(1.5,((row.end-row.start+86400000)/range.span)*100),category=isBlocked(row.task)?"blocked":isDone(row.task)?"done":"active";return `<div style="display:grid;grid-template-columns:minmax(150px,24%) 1fr;gap:10px;align-items:center;margin:8px 0"><button type="button" class="link" data-project-planning-task="${esc(row.task.id)}">${esc(row.task.title||row.task.name||row.task.id)}</button><div style="position:relative;height:24px;background:var(--surface-subtle,#202823)" aria-label="${esc(row.task.title||row.task.id)} ${taskProgress(row.task)} percent"><span class="project-gantt-bar ${category}" style="position:absolute;left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;min-width:8px;height:20px;border:1px solid currentColor;border-radius:4px;text-align:center;overflow:hidden">${taskProgress(row.task)}%</span></div></div>`}).join("")}</div></div>`;
 }
 function render(){
  document.querySelectorAll("[data-project-planning-view]").forEach(button=>button.setAttribute("aria-selected",String(button.dataset.projectPlanningView===state.view)));
  if(state.view==="kanban")renderKanban();else if(state.view==="gantt")renderGantt();else renderOverview();
  const message=q("project-core-progress-message");if(message){message.textContent=state.canEdit?"":"Planning is read-only for this project.";message.classList.remove("error")}
 }
 async function authority(){
  state.canEdit=false;if(!state.projectId){render();return}
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});state.canEdit=caps?.actions?.edit===true;render()}catch(error){state.canEdit=false;render();emitError(error,"Project permissions could not be loaded.")}
 }
 async function moveTask(taskId,statusId){
  if(!state.canEdit||!taskId||!statusId)return;
  try{
   await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`,{method:"PATCH",purpose:"research",body:JSON.stringify({project_id:state.projectId,status_id:statusId})});
   document.dispatchEvent(new CustomEvent("fieldora:project-work-changed",{detail:{module_id:moduleId,project_id:state.projectId,kind:"task",item_id:taskId}}));
  }catch(error){emitError(error,"Task status could not be changed.");await refresh()}
 }
 async function refresh(){
  if(!ensureSurface())return;const pid=state.projectId||window.FieldoraProjects?.currentProject?.()||"";state.projectId=pid;
  if(!pid){state.project=null;state.tasks=[];state.statuses=[];render();return}
  try{
   const encoded=encodeURIComponent(pid);
   const [projectResult,taskResult,statusResult]=await Promise.all([api("/api/v1/projects",{purpose:"research"}),api(`/api/v1/tasks?project_id=${encoded}`,{purpose:"research"}),api(`/api/v1/project-statuses?project_id=${encoded}`,{purpose:"research"})]);
   state.project=(projectResult.items||[]).find(item=>String(item.id)===String(pid))||null;state.tasks=taskResult.items||[];state.statuses=statusResult.items||[];render();await authority();
  }catch(error){state.project=null;state.tasks=[];state.statuses=[];render();emitError(error,"Project planning could not be loaded.")}
 }
 function setView(view){state.view=["overview","kanban","gantt"].includes(view)?view:"overview";render()}
 function inspectTask(taskId){if(taskId)document.dispatchEvent(new CustomEvent("fieldora:project-task-edit-request",{detail:{module_id:moduleId,project_id:state.projectId,task_id:taskId}}))}
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  q("project-core-progress-refresh")?.addEventListener("click",refresh,{signal});
  q("project-core-progress")?.addEventListener("click",event=>{const tab=event.target.closest?.("[data-project-planning-view]"),task=event.target.closest?.("[data-project-planning-task]");if(tab)setView(tab.dataset.projectPlanningView);else if(task)inspectTask(task.dataset.projectPlanningTask)},{signal});
  q("project-core-progress")?.addEventListener("change",event=>{const select=event.target.closest?.("[data-project-kanban-status]");if(select)moveTask(select.dataset.projectKanbanStatus,select.value)},{signal});
  q("project-core-progress")?.addEventListener("dragstart",event=>{const task=event.target.closest?.("[data-project-kanban-task]");if(task&&state.canEdit)event.dataTransfer?.setData("text/x-fieldora-task-id",task.dataset.projectKanbanTask)},{signal});
  q("project-core-progress")?.addEventListener("dragover",event=>{if(state.canEdit&&event.target.closest?.("[data-project-kanban-drop]"))event.preventDefault()},{signal});
  q("project-core-progress")?.addEventListener("drop",event=>{const drop=event.target.closest?.("[data-project-kanban-drop]");if(!drop||!state.canEdit)return;event.preventDefault();const taskId=event.dataTransfer?.getData("text/x-fieldora-task-id")||"";moveTask(taskId,drop.dataset.projectKanbanDrop)},{signal});
  state.projectId=window.FieldoraProjects?.currentProject?.()||"";refresh();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";refresh()});
 document.addEventListener("fieldora:project-work-changed",event=>{if(event.detail?.project_id===state.projectId)refresh()});
 document.addEventListener("fieldora:project-lifecycle-changed",event=>{if(event.detail?.project_id===state.projectId)refresh()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectProgress=Object.freeze({mount,unmount,refresh,setView,moveTask});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_progress_module_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Projects/Core progress/planning adapter exactly once."""

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
    """Compose the independently owned Project progress/planning presentation."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_progress_module_response(target, response)
