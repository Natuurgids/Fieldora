"""Browser navigation compatibility for the managed Fieldora web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_NAVIGATION_WEB_PATCH = bytes(
    r"""

/* Fieldora browser workspace routing, tab rendering and cross-screen wiring. */
(()=>{
 if(window.__fieldoraNavigationWired)return;window.__fieldoraNavigationWired=true;
 const q=id=>document.getElementById(id);
 const oldShowPage=showPage;
 const pageExists=name=>Boolean(q(`page-${name}`));
 let applyingHistory=false;
 showPage=function(name){
  oldShowPage(name);
  if(!applyingHistory&&pageExists(name)&&location.hash!==`#${name}`){
   history.pushState({fieldoraPage:name},"",`#${name}`);
  }
 };
 function routeFromLocation(){
  const name=(location.hash||"#home").slice(1);
  if(!pageExists(name))return;
  applyingHistory=true;try{oldShowPage(name)}finally{applyingHistory=false}
 }
 window.addEventListener("popstate",routeFromLocation);
 window.addEventListener("hashchange",routeFromLocation);
 setTimeout(routeFromLocation,0);

 function selectTab(buttons,selected){
  buttons.forEach(button=>{
   const active=button===selected;
   button.classList.toggle("primary",active);
   button.setAttribute("aria-selected",String(active));
   button.setAttribute("role","tab");
  });
 }

 /* Projects & Portfolio used to change only the selected button.  Render a
    genuinely different working representation for every advertised view. */
 const oldLoadPortfolio=loadPortfolio;
 function portfolioState(){
  const list=q("portfolio-list");
  const tasks=JSON.parse(list?.dataset.tasks||"[]");
  const phases=JSON.parse(list?.dataset.phases||"[]");
  const sprints=JSON.parse(list?.dataset.sprints||"[]");
  const scope=q("portfolio-scope")?.value||"all";
  let visibleProjects=projects;
  if(scope==="mine"&&me){
   visibleProjects=projects.filter(p=>
    !p.owner_id||p.owner_id===me.identity_id||
    tasks.some(t=>t.project_id===p.id&&t.assignee_id===me.identity_id)
   );
  }
  const projectIds=new Set(visibleProjects.map(p=>p.id));
  return {
   list,tasks:tasks.filter(t=>projectIds.has(t.project_id)),
   phases:phases.filter(p=>projectIds.has(p.project_id)),
   sprints:sprints.filter(s=>projectIds.has(s.project_id)),visibleProjects
  };
 }
 function portfolioRow(item,kind,label,detail=""){
  return `<div class="row" data-portfolio-id="${esc(item.id)}" data-kind="${kind}"><strong>${esc(recordName(item))}</strong><span>${esc(label)}</span><span>${esc(detail)}</span></div>`;
 }
 function renderPortfolioView(){
  const state=portfolioState(),list=state.list;if(!list)return;
  list.dataset.renderedView=portfolioView;
  if(portfolioView==="hierarchy")return;
  if(portfolioView==="kanban"){
   const statuses=[...new Set(state.tasks.map(t=>t.status||"unspecified"))];
   list.innerHTML=statuses.length?`<div class="grid portfolio-board">${statuses.map(status=>{
    const matching=state.tasks.filter(t=>(t.status||"unspecified")===status);
    return `<section class="card"><h3>${esc(status)}</h3>${matching.map(t=>portfolioRow(t,"task",t.assignee_id||"Unassigned",t.sprint_id||"")).join("")||'<p class="empty">No tasks.</p>'}</section>`;
   }).join("")}</div>`:'<p class="empty">No tasks available for this scope.</p>';
   return;
  }
  if(portfolioView==="grid"){
   list.innerHTML=state.visibleProjects.length?`<div class="grid">${state.visibleProjects.map(project=>{
    const projectTasks=state.tasks.filter(t=>t.project_id===project.id);
    const projectPhases=state.phases.filter(p=>p.project_id===project.id);
    return `<article class="card" data-portfolio-id="${esc(project.id)}" data-kind="project"><h3>${esc(recordName(project))}</h3><p>${projectPhases.length} phases · ${projectTasks.length} tasks</p><p class="pill">${esc(project.status||"active")}</p></article>`;
   }).join("")}</div>`:'<p class="empty">No accessible projects.</p>';
   return;
  }
  if(portfolioView==="gantt"){
   const scheduled=[...state.phases.map(p=>({...p,__kind:"phase"})),...state.tasks.map(t=>({...t,__kind:"task"}))];
   list.innerHTML=scheduled.length?scheduled.map(item=>portfolioRow(
    item,item.__kind,
    item.starts_at||item.start_date||"Unscheduled",
    item.ends_at||item.end_date||item.due_date||"No end date"
   )).join(""):'<p class="empty">No scheduled work.</p>';
   return;
  }
  if(portfolioView==="workload"){
   const byAssignee=new Map();
   state.tasks.forEach(task=>{
    const assignee=task.assignee_id||"Unassigned";
    if(!byAssignee.has(assignee))byAssignee.set(assignee,[]);
    byAssignee.get(assignee).push(task);
   });
   list.innerHTML=byAssignee.size?[...byAssignee.entries()].map(([assignee,tasks])=>{
    const estimated=tasks.reduce((sum,t)=>sum+Number(t.manual_estimate||0),0);
    const realized=tasks.reduce((sum,t)=>sum+Number(t.realized||0),0);
    return `<section class="card"><h3>${esc(assignee)}</h3><p>${tasks.length} tasks · ${estimated} h planned · ${realized} h realized</p>${tasks.map(t=>portfolioRow(t,"task",t.status||"",`${Number(t.manual_estimate||0)} h`)).join("")}</section>`;
   }).join(""):'<p class="empty">No workload assignments.</p>';
   return;
  }
  if(portfolioView==="budget"){
   list.innerHTML=state.visibleProjects.length?state.visibleProjects.map(project=>{
    const projectTasks=state.tasks.filter(t=>t.project_id===project.id);
    const planned=projectTasks.reduce((sum,t)=>sum+Number(t.manual_estimate||0),0);
    const realized=projectTasks.reduce((sum,t)=>sum+Number(t.realized||0),0);
    const budget=project.budget??project.budget_amount??project.planned_budget;
    const budgetText=budget==null?"Budget not recorded":`Budget ${budget}`;
    return `<article class="card" data-portfolio-id="${esc(project.id)}" data-kind="project"><h3>${esc(recordName(project))}</h3><p>${esc(budgetText)}</p><p>${planned} h planned · ${realized} h realized</p></article>`;
   }).join(""):'<p class="empty">No accessible projects.</p>';
  }
 }
 loadPortfolio=async function(){
  await oldLoadPortfolio();
  renderPortfolioView();
  document.querySelectorAll('#portfolio-list [data-kind="project"]').forEach(row=>{
   row.setAttribute("role","button");row.tabIndex=0;row.title="Open project workspace";
  });
 };
 const portfolioTabs=[...document.querySelectorAll("[data-portfolio-view]")];
 portfolioTabs.forEach(button=>{
  button.onclick=()=>{
   portfolioView=button.dataset.portfolioView;
   selectTab(portfolioTabs,button);
   loadPortfolio();
  };
 });
 if(portfolioTabs.length)selectTab(portfolioTabs,portfolioTabs.find(b=>b.dataset.portfolioView===portfolioView)||portfolioTabs[0]);

 /* Knowledge tabs previously had no state or handlers at all. */
 let knowledgeView="review";
 const knowledgeTabs=[...document.querySelectorAll("#page-knowledge .tabs button")];
 if(knowledgeTabs[0])knowledgeTabs[0].dataset.knowledgeView="review";
 if(knowledgeTabs[1])knowledgeTabs[1].dataset.knowledgeView="accepted";
 function renderKnowledgeView(){
  const reviewStates=new Set(["pending_review","needs_review","disputed","deferred"]);
  const shown=knowledge.filter(item=>knowledgeView==="accepted"?item.status==="accepted":reviewStates.has(item.status||"pending_review"));
  const empty=knowledgeView==="accepted"?"No accepted knowledge.":"No knowledge awaiting review.";
  cards("knowledge-list",shown,k=>`<div class="row" data-knowledge="${esc(k.id)}"><strong>${esc(k.identification||k.name||"Result")}</strong><span>${esc(k.producer||"")}</span><span>${k.confidence==null?"":Math.round(k.confidence*100)+"%"}</span><span class="pill">${esc(k.status||"pending_review")}</span></div>`,empty);
  const list=q("knowledge-list");if(list)list.dataset.renderedView=knowledgeView;
 }
 const oldLoadKnowledge=loadKnowledge;
 loadKnowledge=async function(){await oldLoadKnowledge();renderKnowledgeView()};
 knowledgeTabs.forEach(button=>{
  button.onclick=()=>{
   knowledgeView=button.dataset.knowledgeView;
   selectTab(knowledgeTabs,button);
   renderKnowledgeView();
  };
 });
 if(knowledgeTabs.length)selectTab(knowledgeTabs,knowledgeTabs[0]);

 /* Normalize all remaining functional tab groups for accessibility and make
    their active state testable without changing their existing data logic. */
 ["media-filter","observation-filter","research-domain","operations-domain"].forEach(key=>{
  const buttons=[...document.querySelectorAll(`[data-${key}]`)];
  buttons.forEach(button=>{
   const oldClick=button.onclick;
   button.onclick=event=>{
    if(oldClick)oldClick.call(button,event);
    selectTab(buttons,button);
   };
  });
  if(buttons.length)selectTab(buttons,buttons.find(b=>b.classList.contains("primary"))||buttons[0]);
 });
 const contractTabs=[q("contracts-refresh"),q("approvals-refresh"),q("expiry-refresh")].filter(Boolean);
 contractTabs.forEach(button=>{
  const oldClick=button.onclick;
  button.onclick=event=>{
   if(oldClick)oldClick.call(button,event);
   selectTab(contractTabs,button);
  };
 });
 if(contractTabs.length)selectTab(contractTabs,contractTabs[0]);

 const portfolio=q("portfolio-list");
 if(portfolio){
  const oldPortfolioClick=portfolio.onclick;
  portfolio.onclick=e=>{
   if(oldPortfolioClick)oldPortfolioClick(e);
   const row=e.target.closest('[data-portfolio-id][data-kind="project"]');
   if(!row)return;
   const id=row.dataset.portfolioId;
   const detail=q("portfolio-detail");
   if(detail){
    const old=detail.querySelector("[data-open-project-workspace]");if(old)old.remove();
    const open=document.createElement("button");open.className="primary section";
    open.dataset.openProjectWorkspace="true";
    open.textContent="Open project workspace";
    open.onclick=()=>openProject(id);
    detail.appendChild(open);
   }
  };
  portfolio.addEventListener("keydown",e=>{
   if(e.key!=="Enter"&&e.key!==" ")return;
   const row=e.target.closest('[data-portfolio-id][data-kind="project"]');
   if(row){e.preventDefault();openProject(row.dataset.portfolioId)}
  });
 }

 const operations=q("operations-list");
 if(operations){
  const oldOperationsClick=operations.onclick;
  operations.onclick=e=>{
   if(oldOperationsClick)oldOperationsClick(e);
   const row=e.target.closest("[data-operations-id]");if(!row)return;
   const items=JSON.parse(operations.dataset.records||"[]");
   const item=items.find(x=>x.id===row.dataset.operationsId);
   if(!item?.project_id)return;
   const detail=q("operations-detail");if(!detail)return;
   const old=detail.querySelector("[data-open-related-project]");if(old)old.remove();
   const open=document.createElement("button");open.className="primary section";
   open.dataset.openRelatedProject="true";
   open.textContent="Open related project";
   open.onclick=()=>openProject(item.project_id);
   detail.appendChild(open);
  };
 }

 document.querySelectorAll(".nav[data-page]").forEach(b=>{
  b.title=b.title||`Open ${b.textContent.trim()}`;
 });
})();
""",
    "utf-8",
)


def patch_navigation_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _NAVIGATION_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _NAVIGATION_WEB_PATCH,
        response.content_type,
        response.headers,
    )
