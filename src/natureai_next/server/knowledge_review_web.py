"""Browser rendering and explicit actions for governed Knowledge proposals."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_KNOWLEDGE_REVIEW_PATCH = bytes(
    r"""

/* Fieldora WEB-037/043: Knowledge proposals remain provenance-bearing review objects. */
(()=>{
 if(window.__fieldoraKnowledgeGovernanceWired)return;
 window.__fieldoraKnowledgeGovernanceWired=true;
 const page=document.getElementById("page-knowledge");if(!page)return;
 const byId=id=>document.getElementById(id);
 const html=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
 const candidateLabel=item=>item?.candidate?.value?.scientific_name||item?.candidate?.value?.label||item?.candidate?.scientific_name||item?.candidate?.label||"Identification proposal";
 const sourceLabel=item=>item?.source_snapshot?.producer_name||item?.provider_key||"unknown producer";
 const sourceDetail=item=>item?.source_snapshot?.source_name||item?.source_snapshot?.producer_version||item?.source_snapshot?.source_version||"source snapshot retained";

 let governedKnowledge=[];
 const legacyRender=typeof renderKnowledge==="function"?renderKnowledge:null;
 const legacyLoad=typeof loadKnowledge==="function"?loadKnowledge:null;

 function targetList(){
  return byId("knowledge-list")||byId("knowledge-results")||page.querySelector("[data-knowledge-list]")||page.querySelector(".knowledge-list");
 }
 function renderGovernedKnowledge(){
  const target=targetList();
  if(!target){if(legacyRender)legacyRender();return}
  const query=(byId("knowledge-search")?.value||"").toLowerCase();
  const shown=governedKnowledge.filter(item=>JSON.stringify(item).toLowerCase().includes(query));
  target.innerHTML=shown.length?shown.map(item=>{
   const state=item.review_state||"pending",reviewable=state==="pending"||state==="deferred";
   const canonical=item.canonical;
   const history=(item.review_actions||[]).map(action=>`${html(action.from_state||"")} → ${html(action.to_state||action.action||"")} · ${html(action.actor_identity_id||"unknown reviewer")}`).join("<br>");
   return `<article class="card knowledge-governed-proposal" data-knowledge-proposal="${html(item.id)}">
    <div class="row"><strong>${html(candidateLabel(item))}</strong><span class="pill">${html(state)}</span></div>
    <p class="muted"><strong>Provenance</strong> · ${html(sourceLabel(item))} · ${html(sourceDetail(item))}</p>
    <p class="muted">Provider ${html(item.provider_key||"unknown")} · proposal ${html(item.id)} · revision ${html(item.revision||1)}</p>
    ${history?`<p class="muted"><strong>Review history</strong><br>${history}</p>`:""}
    ${canonical?`<p><strong>Accepted conclusion</strong> · ${html(candidateLabel(canonical))}</p><p class="muted">Trace: proposal ${html(canonical.source_suggestion_public_id)} · acceptance action ${html(canonical.acceptance_action_public_id)}</p>`:""}
    ${reviewable?`<div class="actions"><button type="button" data-knowledge-review="accept">Accept</button><button type="button" data-knowledge-review="reject">Reject</button><button type="button" data-knowledge-review="defer">Defer</button></div>`:""}
   </article>`;
  }).join(""):'<p class="muted">No governed Knowledge proposals in this view.</p>';
 }

 loadKnowledge=async function(){
  try{
   governedKnowledge=(await api("/api/v1/knowledge")).items||[];
   if(typeof knowledge!=="undefined")knowledge=governedKnowledge;
   renderGovernedKnowledge();
  }catch(error){
   const target=targetList();if(target)target.innerHTML=`<p class="muted">${html(error.message)}</p>`;
   else if(legacyLoad)await legacyLoad();
  }
 };
 renderKnowledge=renderGovernedKnowledge;

 async function reviewProposal(item,action){
  const result=await api(`/api/v1/knowledge/${encodeURIComponent(item.id)}/review`,{
   method:"POST",headers:{"If-Match":String(item.revision||1)},body:JSON.stringify({action})
  });
  const index=governedKnowledge.findIndex(value=>value.id===item.id);
  if(index>=0)governedKnowledge[index]={...result.item,revision:result.revision};
  renderGovernedKnowledge();
 }
 page.addEventListener("click",async event=>{
  const button=event.target.closest("[data-knowledge-review]");if(!button)return;
  const card=button.closest("[data-knowledge-proposal]");
  const item=governedKnowledge.find(value=>value.id===card?.dataset.knowledgeProposal);if(!item)return;
  button.disabled=true;
  try{await reviewProposal(item,button.dataset.knowledgeReview)}
  catch(error){button.disabled=false;window.alert(error.message)}
 });
 byId("knowledge-search")?.addEventListener("input",renderGovernedKnowledge);

 /* WEB-043: the legacy creation form used caller-owned IDs and review state. Turn it
    into the governed proposal action: the server owns proposal identity, submitter,
    revision and review state while the browser supplies explicit subject/candidate
    and a retained source snapshot. */
 saveKnowledge=async function(){
  const projectId=(byId("knowledge-project")?.value||"").trim();
  const observationId=(byId("knowledge-observation")?.value||"").trim();
  const producer=(byId("knowledge-producer")?.value||"").trim();
  const identification=(byId("knowledge-name")?.value||"").trim();
  const confidenceText=(byId("knowledge-confidence")?.value||"").trim();
  if(!projectId||!observationId||!producer||!identification){
   status("knowledge-status","Project, observation, producer/source, and identification are required.",true);return;
  }
  const confidence=confidenceText===""?null:Number(confidenceText);
  if(confidence!==null&&(!Number.isFinite(confidence)||confidence<0||confidence>1)){
   status("knowledge-status","Confidence must be between 0 and 1.",true);return;
  }
  const proposal={
   project_id:projectId,
   provider_key:producer,
   subject:{type:"observation",id:observationId},
   candidate:{type:"identification",value:{scientific_name:identification,confidence}},
   source_snapshot:{
    producer_name:producer,
    producer_version:"unspecified",
    source_name:"Fieldora managed-web identification form"
   }
  };
  try{
   await api("/api/v1/knowledge",{method:"POST",body:JSON.stringify(proposal)});
   status("knowledge-status","Identification proposal submitted for review.");
   await loadKnowledge();
  }catch(error){status("knowledge-status",error.message,true)}
 };
 const saveButton=byId("save-knowledge");
 if(saveButton){
  saveButton.textContent="Submit identification proposal";
  saveButton.onclick=saveKnowledge;
 }
 const stateInput=byId("knowledge-state");
 if(stateInput?.closest("label"))stateInput.closest("label").remove();
 const addHeading=page.querySelector("#save-knowledge")?.closest(".card")?.querySelector("h2");
 if(addHeading)addHeading.textContent="Add human or external identification proposal";

 /* The legacy Run analysis button queued rebuild_search, which is index maintenance,
    not a scientific or AI analysis task. Hide the misleading action until a real
    provenance-bearing analysis job contract exists. Search remains available. */
 byId("run-analysis")?.remove();

 const addPanel=byId("knowledge-add-panel")||byId("knowledge-status")?.closest(".card");
 if(addPanel&&!byId("knowledge-governance-note")){
  const note=document.createElement("p");note.id="knowledge-governance-note";note.className="muted";
  note.textContent="New identifications are proposals. Fieldora assigns identity, submitter and revision; acceptance is a separate governed review action.";
  addPanel.prepend(note);
 }
})();
""",
    "utf-8",
)


def patch_knowledge_review_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append Knowledge governance behavior to the managed app bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _KNOWLEDGE_REVIEW_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _KNOWLEDGE_REVIEW_PATCH,
        response.content_type,
        response.headers,
    )
