"""Module-owned Projects browser adapter for the managed Fieldora web client.

The desktop-density cockpit markup remains transitional while Projects/Core
consumes canonical Project context and work-data services to render the Project
hierarchy, center views, inspector feedback and evidence surface. Portfolio
remains a separate module and no longer provides the Projects work surface.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_CORE_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-CORE-MODULE: module-owned Projects browser adapter. */
(()=>{
 if(window.__fieldoraProjectCoreModuleWired)return;window.__fieldoraProjectCoreModuleWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",centerView:"work",scope:"all",evidence:[],phases:[],tasks:[],sprints:[],allocations:[],workSelection:null};
 const escProject=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const projectList=()=>window.FieldoraModuleContracts?.resolve?.("projects.list.read")||null;
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 const workData=()=>window.FieldoraModuleContracts?.resolve?.("projects.work-data.service")||null;
 const evidenceData=()=>window.FieldoraModuleContracts?.resolve?.("projects.evidence.service")||null;
 const projectItems=()=>projectList()?.items?.()||[];
 const projectById=id=>projectItems().find(project=>project.id===id)||null;
 function status(message,error=false){
  const page=q("page-projects");if(!page)return;
  let node=q("project-core-module-status");
  if(!node){node=document.createElement("p");node.id="project-core-module-status";node.className="status";page.querySelector(".top")?.after(node)}
  node.textContent=message||"";node.classList.toggle("error",Boolean(error));
 }
 function moduleError(error,fallback){
  const message=error?.message||fallback;status(message,true);
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(message)}}));
 }
 function visibleProjects(){
  const needle=(q("project-tree-filter")?.value||"").trim().toLowerCase();
  let visible=projectItems();
  if(state.scope==="mine"&&typeof me!=="undefined"&&me?.identity_id){
   const assigned=new Set(state.tasks.filter(task=>task.assignee_id===me.identity_id||task.owner_id===me.identity_id).map(task=>task.project_id));
   const mine=visible.filter(project=>project.owner_id===me.identity_id||project.created_by_id===me.identity_id||project.manager_id===me.identity_id||assigned.has(project.id));
   visible=mine;
  }
  return needle?visible.filter(project=>JSON.stringify(project).toLowerCase().includes(needle)):visible;
 }
 function renderTree(){
  const host=q("project-cockpit-tree");if(!host)return;
  const visible=visibleProjects();
  host.innerHTML=`<div class="tree-group"><div class="tree-label">Projects</div>${visible.map(project=>`<button type="button" class="tree-item" data-project-tree="${escProject(project.id)}" aria-selected="${project.id===state.projectId}"><span class="tree-icon">▦</span><span>${escProject(project.name||project.title||project.id)}</span></button>`).join("")||'<div class="empty">No accessible projects.</div>'}</div><div class="tree-group"><div class="tree-label">Saved views</div><button type="button" class="tree-item" data-project-scope="mine" aria-selected="${state.scope==="mine"}"><span class="tree-icon">★</span>My work</button><button type="button" class="tree-item" data-project-scope="all" aria-selected="${state.scope==="all"}"><span class="tree-icon">≡</span>All accessible</button></div>`;
 }
 function ensureWorkSurface(){
  const center=q("project-workspace-work");if(!center)return null;
  let host=q("project-core-work-hierarchy");
  if(!host){host=document.createElement("section");host.id="project-core-work-hierarchy";host.className="card section";host.innerHTML='<div class="top"><div><h2>Project work</h2><p class="muted">Phases, tasks, milestones and subtasks for the selected project.</p></div></div><div id="project-core-work-list"></div>';center.prepend(host)}
  return host;
 }
 function workRow(item,kind,depth,label){
  const selected=state.workSelection?.kind===kind&&state.workSelection?.id===item.id;
  const due=item.due_date||item.end_date||"";
  const display=kind==="task"&&item.milestone?`Milestone · ${label}`:label;
  return `<button type="button" class="row" data-project-work-kind="${escProject(kind)}" data-project-work-id="${escProject(item.id)}" aria-selected="${selected}"><strong>${" ".repeat(depth)}${depth?"↳ ":""}${escProject(display)}</strong><span>${escProject(kind==="task"?(item.assignee_id||item.owner_id||""):kind[0].toUpperCase()+kind.slice(1))}</span><span>${escProject(item.status||due||"active")}</span></button>`;
 }
 function renderWork(){
  ensureWorkSurface();const host=q("project-core-work-list");if(!host)return;
  const pid=state.projectId;if(!pid){host.innerHTML='<div class="empty">Select a project to view its work hierarchy.</div>';return}
  const phases=state.phases.filter(item=>item.project_id===pid),tasks=state.tasks.filter(item=>item.project_id===pid),sprints=state.sprints.filter(item=>item.project_id===pid),allocations=state.allocations.filter(item=>item.project_id===pid);
  const children=new Map();tasks.forEach(task=>{const parent=String(task.parent_task_id||"");if(!children.has(parent))children.set(parent,[]);children.get(parent).push(task)});
  const rows=[];
  const addTasks=(items,depth)=>items.forEach(task=>{rows.push(workRow(task,"task",depth,task.name||task.title||task.id));addTasks(children.get(String(task.id))||[],depth+1)});
  phases.forEach(phase=>{rows.push(workRow(phase,"phase",0,phase.name||phase.title||phase.id));addTasks(tasks.filter(task=>task.phase_id===phase.id&&!task.parent_task_id),1)});
  addTasks(tasks.filter(task=>!task.phase_id&&!task.parent_task_id),0);
  sprints.forEach(sprint=>rows.push(workRow(sprint,"sprint",0,sprint.name||sprint.title||sprint.id)));
  allocations.forEach(allocation=>rows.push(workRow(allocation,"allocation",0,allocation.role||allocation.user_id||allocation.id)));
  host.innerHTML=rows.join("")||'<div class="empty">No phases, tasks, sprints or allocations exist for this project.</div>';
 }
 async function loadWork(){
  state.phases=[];state.tasks=[];state.sprints=[];state.allocations=[];renderWork();if(!state.projectId)return;
  const service=workData();if(!service){moduleError(new Error("Project work-data service is unavailable."),"Project work could not be loaded.");return}
  try{
   const snapshot=await service.load(state.projectId);
   state.phases=[...(snapshot?.phases||[])];state.tasks=[...(snapshot?.tasks||[])];state.sprints=[...(snapshot?.sprints||[])];state.allocations=[...(snapshot?.allocations||[])];renderWork();renderTree();status("");
  }catch(error){renderWork();moduleError(error,"Project work could not be loaded.")}
 }
 function selectInspector(key){
  const host=q("project-desktop-cockpit")?.querySelector(".cockpit-right");if(!host)return;
  host.querySelectorAll(".inspector-tabs [data-inspector]").forEach(button=>button.setAttribute("aria-selected",String(button.dataset.inspector===key)));
  host.querySelectorAll('.inspector-panel[id^="project-inspector-"]').forEach(panel=>panel.hidden=panel.id!==`project-inspector-${key}`);
 }
 function renderInspector(record){
  const metadata=q("project-inspector-metadata"),map=q("project-inspector-map"),activity=q("project-inspector-activity"),title=q("project-cockpit-title");
  if(title)title.textContent=record?.name||record?.title||"Project workspace";
  if(!record){if(metadata)metadata.innerHTML='<div class="empty">Select a project or work item.</div>';if(map)map.innerHTML='<div class="empty">Select a project to inspect its spatial context.</div>';if(activity)activity.innerHTML='<div class="empty">Select a record.</div>';return}
  if(metadata)metadata.innerHTML=`<h3>${escProject(record.name||record.title||record.id)}</h3><pre>${escProject(JSON.stringify(record,null,2))}</pre>`;
  if(map)map.innerHTML=`<div class="facility-map-stage"><h3>Project map</h3><p>${escProject(record.name||record.title||record.id)}</p><p class="muted">${escProject(record.research_area||record.location||record.geography||"No spatial boundary has been recorded for this project yet.")}</p><p class="muted">Map packages remain governed by Fieldora map installation and offline-map services.</p></div>`;
  if(activity)activity.innerHTML=`<h3>Record activity</h3><p><strong>Status</strong> ${escProject(record.status||"active")}</p><p><strong>Created</strong> ${escProject(record.created_at||record.created||"—")}</p><p><strong>Updated</strong> ${escProject(record.updated_at||record.modified_at||record.updated||"—")}</p><p class="muted">Authoritative security and change history remains in the governed audit log.</p>`;
 }
 function renderEvidence(){
  const host=q("project-workspace-evidence");if(!host)return;
  host.innerHTML=state.evidence.length?`<div class="project-evidence-grid">${state.evidence.map(item=>`<article class="project-evidence" data-media="${escProject(item.media_id)}"><div class="thumb">${String(item.mime_type||"").startsWith("image/")?"▧":String(item.mime_type||"").startsWith("audio/")?"≋":String(item.mime_type||"").startsWith("video/")?"▷":"▤"}</div><strong>${escProject(item.filename||item.name||item.media_id)}</strong><small class="muted">${escProject(item.mime_type||"")}</small></article>`).join("")}</div>`:'<div class="empty">No evidence is linked to the selected project.</div>';
 }
 async function loadEvidence(){
  state.evidence=[];renderEvidence();if(!state.projectId)return;
  const service=evidenceData();if(!service){moduleError(new Error("Project evidence service is unavailable."),"Project evidence could not be loaded.");return}
  try{state.evidence=[...(await service.projectItems(state.projectId))];renderEvidence();status("")}catch(error){renderEvidence();moduleError(error,"Project evidence could not be loaded.")}
 }
 async function applyProjectContext(id){
  const requested=String(id||"");
  if(state.projectId===requested){renderTree();return true}
  state.projectId=requested;state.workSelection=null;
  if(q("work-project"))q("work-project").value=state.projectId;
  renderTree();renderInspector(projectById(state.projectId));selectInspector("properties");
  await Promise.all([loadWork(),loadEvidence()]);return true;
 }
 function requestProject(id){
  const context=projectContext();if(!context?.select){moduleError(new Error("Project context service is unavailable."),"Project could not be selected.");return false}
  const selected=context.select(id);if(selected===false){status("That project is no longer accessible.",true);return false}
  return true;
 }
 async function loadProjects(){
  const list=projectList();if(!list){renderTree();return false}
  try{
   await list.refresh();
   const context=projectContext();if(!context){moduleError(new Error("Project context service is unavailable."),"Projects could not be loaded.");return false}
   await applyProjectContext(context.current?.()||"");return true;
  }catch(error){renderTree();moduleError(error,"Projects could not be loaded.");return false}
 }
 function setCenter(view){
  state.centerView=view==="evidence"?"evidence":"work";const work=q("project-workspace-work"),evidence=q("project-workspace-evidence");
  if(work)work.hidden=state.centerView!=="work";if(evidence)evidence.hidden=state.centerView!=="evidence";
  document.querySelectorAll("[data-project-center]").forEach(button=>button.classList.toggle("primary",button.dataset.projectCenter===state.centerView));
  if(state.centerView==="evidence"&&!state.evidence.length&&state.projectId)loadEvidence();
 }
 function inspectWorkItem(target){
  const row=target?.closest?.("[data-project-work-kind]");if(!row)return false;
  const kind=row.dataset.projectWorkKind,id=row.dataset.projectWorkId;
  const source=kind==="phase"?state.phases:kind==="task"?state.tasks:kind==="sprint"?state.sprints:state.allocations;
  const record=source.find(item=>String(item.id)===String(id));if(!record)return false;
  state.workSelection={kind,id};renderWork();renderInspector(record);selectInspector("properties");return true;
 }
 function mount(){
  if(state.mounted)return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;ensureWorkSurface();
  const legacy=q("portfolio-list")?.closest(".card");if(legacy)legacy.dataset.projectCoreLegacyHidden=String(legacy.hidden),legacy.hidden=true;
  q("project-tree-filter")?.addEventListener("input",renderTree,{signal});
  q("project-cockpit-tree")?.addEventListener("click",event=>{const project=event.target.closest?.("[data-project-tree]"),scope=event.target.closest?.("[data-project-scope]");if(project)requestProject(project.dataset.projectTree);else if(scope){state.scope=scope.dataset.projectScope==="mine"?"mine":"all";renderTree()}},{signal});
  q("project-desktop-cockpit")?.addEventListener("click",event=>{const center=event.target.closest?.("[data-project-center]");if(center)setCenter(center.dataset.projectCenter);else inspectWorkItem(event.target)},{signal});
  renderTree();setCenter(state.centerView);loadProjects();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;const legacy=q("portfolio-list")?.closest(".card");if(legacy&&"projectCoreLegacyHidden" in legacy.dataset){legacy.hidden=legacy.dataset.projectCoreLegacyHidden==="true";delete legacy.dataset.projectCoreLegacyHidden}status("")}
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 document.addEventListener("fieldora:contract-registered",event=>{if(event.detail?.contract==="projects.list.read"&&state.mounted)loadProjects();else if(event.detail?.contract==="projects.context.select"&&state.mounted)applyProjectContext(projectContext()?.current?.()||"")});
 document.addEventListener("fieldora:project-list-changed",()=>{if(state.mounted)renderTree()});
 document.addEventListener("fieldora:project-context-changed",event=>{if(state.mounted)applyProjectContext(event.detail?.project_id||"")});
 document.addEventListener("fieldora:project-work-changed",event=>{if(event.detail?.project_id===state.projectId)loadWork()});
 document.addEventListener("fieldora:project-evidence-changed",event=>{if(event.detail?.project_id===state.projectId)loadEvidence()});
 window.FieldoraProjects=Object.freeze({mount,unmount,selectProject:id=>projectContext()?.select?.(id)??false,setCenter,refreshWork:loadWork,refreshEvidence:loadEvidence,currentProject:()=>String(projectContext()?.current?.()||""),currentView:()=>state.centerView});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_core_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the module-owned Projects adapter exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_CORE_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_CORE_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectCoreModuleWebApiMixin:
    """Compose the independently owned Projects browser adapter."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_core_module_response(target, response)
