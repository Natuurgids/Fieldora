"""Task-oriented Observations and Knowledge web workspaces."""

from natureai_next.server.api import ApiResponse

_SCIENCE_WORKFLOW_PATCH = bytes(
    r"""

/* Fieldora science workflow alignment: separate review/inspection from creation. */
(()=>{
 if(window.__fieldoraScienceWorkflowWired)return;
 window.__fieldoraScienceWorkflowWired=true;
 const q=id=>document.getElementById(id);
 const style=document.createElement("style");
 style.textContent=`
  #observation-review-panel[hidden],#knowledge-review-panel[hidden],#knowledge-add-panel[hidden]{display:none!important}
  #observation-editor .observation-parity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
  #observation-editor .observation-parity-grid .wide{grid-column:1/-1}
 `;
 document.head.appendChild(style);

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

 const observationsPage=q("page-observations");
 if(observationsPage){
  const review=observationsPage.querySelector(".split"),editor=q("observation-editor");
  if(review)review.id="observation-review-panel";
  let observationView="review",editingObservation=null;
  let observationNav=null;
  const intro=document.createElement("p");intro.id="observation-workspace-intro";intro.className="library-workspace-intro";

  if(editor){
   editor.innerHTML=`
    <h3 id="observation-editor-title">New observation</h3>
    <p class="muted">Observations are created from existing governed evidence. Evidence ownership is preserved; the media object is linked, not copied.</p>
    <div class="observation-parity-grid">
     <label>Project<select id="obs-project"></select></label>
     <label>Existing evidence<select id="obs-asset"><option value="">Select governed evidence…</option></select></label>
     <label>Observation type<select id="obs-type"><option value="unknown">Unknown</option><option value="organism">Organism</option><option value="habitat">Habitat</option><option value="landscape">Landscape</option></select></label>
     <label>Count<input id="obs-count" type="number" min="0" step="1"></label>
     <label>Life stage<input id="obs-life-stage" autocomplete="off"></label>
     <label>Sex<input id="obs-sex" autocomplete="off"></label>
     <label class="wide">Behavior<input id="obs-behavior" autocomplete="off"></label>
     <label class="wide">Notes<textarea id="obs-notes" rows="4"></textarea></label>
    </div>
    <div class="actions"><button id="obs-save-aligned" type="button">Save observation</button><button id="obs-cancel-aligned" type="button">Cancel</button></div>
    <p id="obs-save-status" class="muted" aria-live="polite"></p>`;
   projectOptions();
  }

  function setObservationView(view){
   observationView=view;
   if(review)review.hidden=view!=="review";
   if(editor)editor.hidden=view!=="create";
   selectTask(observationNav,view);
   intro.textContent=view==="review"
    ?"Inspect field observations, filter review states, and make explicit governed decisions."
    :editingObservation
      ?"Edit the observation fields while preserving its existing evidence link and revision history."
      :"Create a field observation from existing governed evidence; Fieldora keeps the evidence object canonical and links it without cloning.";
   if(view==="create")q("obs-asset")?.focus();
  }

  async function refreshObservationEvidence(preferred=""){
   const select=q("obs-asset"),project=q("obs-project")?.value||"";
   if(!select)return;
   select.innerHTML='<option value="">Select governed evidence…</option>';
   if(!project)return;
   try{
    const result=await api(`/api/v1/media?limit=500&project_id=${encodeURIComponent(project)}`);
    for(const item of result.items||[]){
     const option=document.createElement("option");option.value=item.media_id;
     option.textContent=`${item.mime_type||"evidence"} · ${item.media_id}`;
     select.appendChild(option);
    }
    if(preferred)select.value=preferred;
   }catch(e){status("obs-save-status",e.message,true)}
  }

  function clearObservationForm(){
   for(const id of ["obs-count","obs-life-stage","obs-sex","obs-behavior","obs-notes"]){if(q(id))q(id).value=""}
   if(q("obs-type"))q("obs-type").value="unknown";
   if(q("obs-asset")){q("obs-asset").disabled=false;q("obs-asset").value=""}
   status("obs-save-status","");
  }

  async function beginObservationCreate(){
   editingObservation=null;clearObservationForm();
   if(q("observation-editor-title"))q("observation-editor-title").textContent="New observation";
   const project=selectedProject||projects[0]?.id||"";
   if(q("obs-project")){q("obs-project").disabled=false;q("obs-project").value=project}
   await refreshObservationEvidence();
   setObservationView("create");
  }

  async function beginObservationEdit(id){
   const item=observations.find(value=>value.id===id);if(!item)return;
   editingObservation=item;
   if(q("observation-editor-title"))q("observation-editor-title").textContent="Edit observation";
   if(q("obs-project")){q("obs-project").value=item.project_id||"";q("obs-project").disabled=true}
   if(q("obs-type"))q("obs-type").value=item.observation_type||"unknown";
   if(q("obs-count"))q("obs-count").value=item.count??"";
   if(q("obs-life-stage"))q("obs-life-stage").value=item.life_stage||"";
   if(q("obs-sex"))q("obs-sex").value=item.sex||"";
   if(q("obs-behavior"))q("obs-behavior").value=item.behavior||"";
   if(q("obs-notes"))q("obs-notes").value=item.notes||"";
   await refreshObservationEvidence(item.asset_id||"");
   if(q("obs-asset"))q("obs-asset").disabled=true;
   setObservationView("create");
  }

  async function saveAlignedObservation(){
   const project=q("obs-project")?.value||"",asset=q("obs-asset")?.value||"";
   if(!project||!asset)return status("obs-save-status","Select a project and existing governed evidence.",true);
   const countText=q("obs-count")?.value??"";
   const changes={
    observation_type:q("obs-type")?.value||"unknown",
    count:countText===""?null:Number(countText),
    life_stage:q("obs-life-stage")?.value||null,
    sex:q("obs-sex")?.value||null,
    behavior:q("obs-behavior")?.value||null,
    notes:q("obs-notes")?.value||null,
   };
   try{
    if(editingObservation){
     await api(`/api/v1/observations/${encodeURIComponent(editingObservation.id)}`,{
      method:"PATCH",headers:{"If-Match":String(editingObservation.revision||1)},body:JSON.stringify(changes)
     });
     status("obs-save-status","Observation updated.");
    }else{
     await api("/api/v1/observations",{method:"POST",body:JSON.stringify({project_id:project,asset_id:asset,...changes})});
     status("obs-save-status","Observation created from existing evidence.");
    }
    editingObservation=null;if(q("obs-project"))q("obs-project").disabled=false;
    await loadObservations();setObservationView("review");
   }catch(e){status("obs-save-status",e.message,true)}
  }

  async function reviewObservation(item,confirmation){
   if(!item)return;
   return api(`/api/v1/observations/${encodeURIComponent(item.id)}`,{
    method:"PATCH",headers:{"If-Match":String(item.revision||1)},body:JSON.stringify({confirmation_state:confirmation})
   });
  }

  observationNav=makeTaskNav(
   observationsPage,"observation-workspace-nav",
   [["review","Review observations"],["create","New observation"]],
   view=>view==="create"?beginObservationCreate():setObservationView("review"),
  );
  observationNav?.after(intro);
  const newObservation=q("new-observation");
  if(newObservation)newObservation.hidden=true;
  q("obs-project")?.addEventListener("change",()=>refreshObservationEvidence());
  q("obs-save-aligned")?.addEventListener("click",saveAlignedObservation);
  q("obs-cancel-aligned")?.addEventListener("click",()=>{editingObservation=null;if(q("obs-project"))q("obs-project").disabled=false;setObservationView("review")});
  q("observation-list")?.addEventListener("click",event=>{
   if(event.target.closest("input[type=checkbox]"))return;
   const row=event.target.closest("[data-observation]");if(row)beginObservationEdit(row.dataset.observation);
  });

  loadObservations=async function(){
   try{observations=(await api("/api/v1/observations")).items;renderObservations()}
   catch(e){cards("observation-list",[],x=>x,e.message)}
  };
  renderObservations=function(){
   const query=(document.querySelector("#page-observations .global-search")?.value||"").toLowerCase();
   const shown=observations.filter(o=>{
    const state=o.confirmation_state||"unconfirmed";
    const filterOk=observationFilter==="all"||state===observationFilter||(observationFilter==="review"&&state==="unconfirmed");
    return filterOk&&JSON.stringify(o).toLowerCase().includes(query);
   });
   cards("observation-list",shown,o=>`<div class="row" data-observation="${esc(o.id)}"><input type="checkbox" data-observation-select="${esc(o.id)}" ${selectedObservations.has(o.id)?"checked":""}><strong>${esc(o.observation_type||"unknown")}</strong><span>${esc(o.asset_id||"")}</span><span>${o.count==null?"":esc(o.count)}</span><span class="pill">${esc(o.confirmation_state||"unconfirmed")}</span></div>`);
  };
  reviewSelected=async function(statusValue){
   const ids=[...selectedObservations];if(!ids.length)return;
   const confirmation=statusValue==="confirmed"?"confirmed":statusValue==="rejected"?"rejected":"unconfirmed";
   for(const id of ids){const item=observations.find(value=>value.id===id);if(item)await reviewObservation(item,confirmation)}
   selectedObservations.clear();await loadObservations();
  };
  acceptOneRejectRest=async function(){
   const ids=[...selectedObservations];if(ids.length!==1)return;
   const chosen=observations.find(value=>value.id===ids[0]);if(!chosen)return;
   const group=observations.filter(value=>value.asset_id===chosen.asset_id);
   for(const item of group)await reviewObservation(item,item.id===chosen.id?"confirmed":"rejected");
   selectedObservations.clear();await loadObservations();
  };
  rejectAllUnconfirmed=async function(){
   const ids=[...selectedObservations];if(!ids.length)return;
   const selected=observations.find(value=>value.id===ids[0]);if(!selected)return;
   for(const item of observations.filter(value=>value.asset_id===selected.asset_id&&value.confirmation_state!=="confirmed"))await reviewObservation(item,"rejected");
   selectedObservations.clear();await loadObservations();
  };

  setObservationView("review");
 }

 const knowledgePage=q("page-knowledge");
 if(knowledgePage){
  const review=knowledgePage.querySelector(".split");
  const add=q("knowledge-status")?.closest(".card");
  if(review)review.id="knowledge-review-panel";
  if(add)add.id="knowledge-add-panel";
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
