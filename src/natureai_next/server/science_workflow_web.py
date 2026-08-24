"""Task-oriented Observations and Knowledge web workspaces."""

from natureai_next.server.api import ApiResponse

_SCIENCE_WORKFLOW_PATCH = bytes(
    r"""

/* Fieldora science workflow alignment: separate review/inspection from creation. */
(()=>{
 if(window.__fieldoraScienceWorkflowWired)return;
 window.__fieldoraScienceWorkflowWired=true;
 const q=id=>document.getElementById(id);

 function makeTaskNav(host,id,entries,onSelect){
  if(!host||q(id))return null;
  const nav=document.createElement("div");
  nav.id=id;nav.className="workspace-subnav";nav.setAttribute("role","tablist");
  entries.forEach(([value,label])=>{
   const button=document.createElement("button");button.type="button";
   button.dataset.taskView=value;button.textContent=label;
   button.onclick=()=>onSelect(value);nav.appendChild(button);
  });
  const top=host.querySelector(".top");if(top)top.after(nav);else host.prepend(nav);
  return nav;
 }
 function selectTask(nav,value){
  nav?.querySelectorAll("[data-task-view]").forEach(button=>
   button.setAttribute("aria-selected",String(button.dataset.taskView===value))
  );
 }

 const observations=q("page-observations");
 if(observations){
  const review=observations.querySelector(".split"),editor=q("observation-editor");
  let observationView="review";
  let observationNav=null;
  const intro=document.createElement("p");intro.id="observation-workspace-intro";intro.className="library-workspace-intro";
  function setObservationView(view){
   observationView=view;
   if(review)review.hidden=view!=="review";
   if(editor)editor.hidden=view!=="create";
   selectTask(observationNav,view);
   intro.textContent=view==="review"
    ?"Inspect field observations, filter review states, and make explicit governed decisions."
    :"Create a field observation and link evidence or project context where appropriate.";
   if(view==="create")q("obs-name")?.focus();
  }
  observationNav=makeTaskNav(
   observations,"observation-workspace-nav",
   [["review","Review observations"],["create","New observation"]],
   setObservationView,
  );
  observationNav?.after(intro);
  const newObservation=q("new-observation");
  if(newObservation)newObservation.hidden=true;
  if(editor){
   new MutationObserver(()=>{
    if(observationView==="create"&&editor.hidden)setObservationView("review");
   }).observe(editor,{attributes:true,attributeFilter:["hidden"]});
  }
  setObservationView("review");
 }

 const knowledgePage=q("page-knowledge");
 if(knowledgePage){
  const review=knowledgePage.querySelector(".split");
  const add=q("knowledge-status")?.closest(".card");
  const search=q("knowledge-search"),run=q("run-analysis");
  let knowledgeView="review";
  let knowledgeNav=null;
  const intro=document.createElement("p");intro.id="knowledge-workspace-intro";intro.className="library-workspace-intro";
  function setKnowledgeView(view){
   knowledgeView=view;
   if(review)review.hidden=view!=="review";
   if(add)add.hidden=view!=="add";
   if(search)search.hidden=view!=="review";
   if(run)run.hidden=view!=="review";
   selectTask(knowledgeNav,view);
   intro.textContent=view==="review"
    ?"Review proposed analyses and accepted knowledge while preserving producer and provenance history."
    :"Add a human or external identification as a provenance-bearing enrichment; acceptance remains an explicit governed state.";
   if(view==="add")q("knowledge-observation")?.focus();
  }
  knowledgeNav=makeTaskNav(
   knowledgePage,"knowledge-workspace-nav",
   [["review","Review knowledge"],["add","Add identification"]],
   setKnowledgeView,
  );
  knowledgeNav?.after(intro);
  setKnowledgeView("review");
 }
})();
""",
    "utf-8",
)


def patch_science_workflow_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _SCIENCE_WORKFLOW_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _SCIENCE_WORKFLOW_PATCH,
        response.content_type,
        response.headers,
    )
