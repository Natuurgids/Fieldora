"""Module-owned Portfolio browser adapter for the managed Fieldora web client.

The Portfolio surface is being migrated out of the shared navigation
compatibility patch.  This adapter owns Portfolio view switching, scope refresh
and project-open interaction without replacing global feature functions.

During migration it may call the existing ``loadPortfolio`` renderer as an
integration dependency so the authoritative server/API flow and established
datasets remain unchanged.  The adapter then renders the selected Portfolio
representation from those published datasets.  Once the underlying Portfolio
API/view-model boundary is extracted, that transitional dependency can be
removed without changing the shell contract.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


_PORTFOLIO_MODULE_PATCH = bytes(
    r"""

/* WEB-PORTFOLIO-MODULE: module-owned Portfolio browser adapter. */
(()=>{
 if(window.__fieldoraPortfolioModuleWired)return;window.__fieldoraPortfolioModuleWired=true;
 const moduleId="portfolio",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,view:"hierarchy"};
 const escPortfolio=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const itemName=item=>item?.name||item?.title||item?.label||item?.id||"Untitled";
 function status(message,error=false){
  const page=q("page-portfolio");if(!page)return;
  let node=q("portfolio-module-status");
  if(!node){node=document.createElement("p");node.id="portfolio-module-status";node.className="status";page.querySelector(".top")?.after(node)}
  node.textContent=message||"";node.classList.toggle("error",Boolean(error));
 }
 function selectTabs(){
  document.querySelectorAll("[data-portfolio-view]").forEach(button=>{
   const active=button.dataset.portfolioView===state.view;
   button.classList.toggle("primary",active);button.setAttribute("role","tab");button.setAttribute("aria-selected",String(active));
  });
 }
 function snapshot(){
  const list=q("portfolio-list"),tasks=JSON.parse(list?.dataset.tasks||"[]"),phases=JSON.parse(list?.dataset.phases||"[]"),sprints=JSON.parse(list?.dataset.sprints||"[]");
  const scope=q("portfolio-scope")?.value||"all",allProjects=Array.isArray(window.projects)?window.projects:[];
  let visibleProjects=allProjects;
  if(scope==="mine"&&window.me){
   visibleProjects=allProjects.filter(project=>!project.owner_id||project.owner_id===window.me.identity_id||tasks.some(task=>task.project_id===project.id&&task.assignee_id===window.me.identity_id));
  }
  const projectIds=new Set(visibleProjects.map(project=>project.id));
  return {list,visibleProjects,tasks:tasks.filter(task=>projectIds.has(task.project_id)),phases:phases.filter(phase=>projectIds.has(phase.project_id)),sprints:sprints.filter(sprint=>projectIds.has(sprint.project_id))};
 }
 function row(item,kind,label,detail=""){
  return `<div class="row" data-portfolio-id="${escPortfolio(item.id)}" data-kind="${kind}"><strong>${escPortfolio(itemName(item))}</strong><span>${escPortfolio(label)}</span><span>${escPortfolio(detail)}</span></div>`;
 }
 function render(){
  const data=snapshot(),list=data.list;if(!list)return;
  list.dataset.renderedView=state.view;
  if(state.view==="hierarchy")return;
  if(state.view==="kanban"){
   const statuses=[...new Set(data.tasks.map(task=>task.status||"unspecified"))];
   list.innerHTML=statuses.length?`<div class="grid portfolio-board">${statuses.map(statusValue=>{const matching=data.tasks.filter(task=>(task.status||"unspecified")===statusValue);return `<section class="card"><h3>${escPortfolio(statusValue)}</h3>${matching.map(task=>row(task,"task",task.assignee_id||"Unassigned",task.sprint_id||"")).join("")||'<p class="empty">No tasks.</p>'}</section>`}).join("")}</div>`:'<p class="empty">No tasks available for this scope.</p>';
   return;
  }
  if(state.view==="grid"){
   list.innerHTML=data.visibleProjects.length?`<div class="grid">${data.visibleProjects.map(project=>{const projectTasks=data.tasks.filter(task=>task.project_id===project.id),projectPhases=data.phases.filter(phase=>phase.project_id===project.id);return `<article class="card" data-portfolio-id="${escPortfolio(project.id)}" data-kind="project"><h3>${escPortfolio(itemName(project))}</h3><p>${projectPhases.length} phases · ${projectTasks.length} tasks</p><p class="pill">${escPortfolio(project.status||"active")}</p></article>`}).join("")}</div>`:'<p class="empty">No accessible projects.</p>';
   return;
  }
  if(state.view==="gantt"){
   const scheduled=[...data.phases.map(item=>({...item,__kind:"phase"})),...data.tasks.map(item=>({...item,__kind:"task"}))];
   list.innerHTML=scheduled.length?scheduled.map(item=>row(item,item.__kind,item.starts_at||item.start_date||"Unscheduled",item.ends_at||item.end_date||item.due_date||"No end date")).join(""):'<p class="empty">No scheduled work.</p>';
   return;
  }
  if(state.view==="workload"){
   const byAssignee=new Map();data.tasks.forEach(task=>{const assignee=task.assignee_id||"Unassigned";if(!byAssignee.has(assignee))byAssignee.set(assignee,[]);byAssignee.get(assignee).push(task)});
   list.innerHTML=byAssignee.size?[...byAssignee.entries()].map(([assignee,tasks])=>{const estimated=tasks.reduce((sum,task)=>sum+Number(task.manual_estimate||0),0),realized=tasks.reduce((sum,task)=>sum+Number(task.realized||0),0);return `<section class="card"><h3>${escPortfolio(assignee)}</h3><p>${tasks.length} tasks · ${estimated} h planned · ${realized} h realized</p>${tasks.map(task=>row(task,"task",task.status||"",`${Number(task.manual_estimate||0)} h`)).join("")}</section>`}).join(""):'<p class="empty">No workload assignments.</p>';
   return;
  }
  if(state.view==="budget"){
   list.innerHTML=data.visibleProjects.length?data.visibleProjects.map(project=>{const projectTasks=data.tasks.filter(task=>task.project_id===project.id),planned=projectTasks.reduce((sum,task)=>sum+Number(task.manual_estimate||0),0),realized=projectTasks.reduce((sum,task)=>sum+Number(task.realized||0),0),budget=project.budget??project.budget_amount??project.planned_budget,budgetText=budget==null?"Budget not recorded":`Budget ${budget}`;return `<article class="card" data-portfolio-id="${escPortfolio(project.id)}" data-kind="project"><h3>${escPortfolio(itemName(project))}</h3><p>${escPortfolio(budgetText)}</p><p>${planned} h planned · ${realized} h realized</p></article>`}).join(""):'<p class="empty">No accessible projects.</p>';
  }
 }
 async function refresh(){
  try{
   if(typeof window.loadPortfolio==="function")await window.loadPortfolio();
   render();selectTabs();status("");
  }catch(error){status(error?.message||"Portfolio could not be loaded.",true);document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(error?.message||error)}}))}
 }
 function openProjectFrom(target){
  const rowNode=target?.closest?.('[data-portfolio-id][data-kind="project"]');if(!rowNode)return false;
  if(typeof window.openProject==="function")window.openProject(rowNode.dataset.portfolioId);return true;
 }
 function mount(){
  if(state.mounted)return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  document.querySelectorAll("[data-portfolio-view]").forEach(button=>button.addEventListener("click",()=>{state.view=button.dataset.portfolioView||"hierarchy";refresh()},{signal}));
  q("portfolio-scope")?.addEventListener("change",refresh,{signal});
  q("portfolio-list")?.addEventListener("click",event=>openProjectFrom(event.target),{signal});
  q("portfolio-list")?.addEventListener("keydown",event=>{if(event.key!=="Enter"&&event.key!==" ")return;if(openProjectFrom(event.target))event.preventDefault()},{signal});
  refresh();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;status("")}
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraPortfolio=Object.freeze({mount,unmount,refresh,currentView:()=>state.view});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_portfolio_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the module-owned Portfolio adapter exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PORTFOLIO_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PORTFOLIO_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class PortfolioModuleWebApiMixin:
    """Compose the independently owned Portfolio browser adapter."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_portfolio_module_response(target, response)
