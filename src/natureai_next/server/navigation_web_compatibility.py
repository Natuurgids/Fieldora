"""Browser navigation compatibility for the managed Fieldora web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_NAVIGATION_WEB_PATCH = bytes(
    r"""

/* Fieldora browser workspace routing and cross-screen wiring. */
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

 const oldLoadPortfolio=loadPortfolio;
 loadPortfolio=async function(){
  await oldLoadPortfolio();
  document.querySelectorAll('#portfolio-list [data-kind="project"]').forEach(row=>{
   row.setAttribute("role","button");row.tabIndex=0;row.title="Open project workspace";
  });
 };
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
    const open=document.createElement("button");open.className="primary section";
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
   const open=document.createElement("button");open.className="primary section";
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
