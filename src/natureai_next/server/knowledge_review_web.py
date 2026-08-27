"""Browser rendering and explicit review actions for governed Knowledge proposals."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_KNOWLEDGE_REVIEW_PATCH = bytes(
    r"""

/* Fieldora WEB-037: Knowledge proposals remain provenance-bearing review objects. */
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
   return `<article class="card knowledge-governed-proposal" data-knowledge-proposal="${html(item.id)}">
    <div class="row"><strong>${html(candidateLabel(item))}</strong><span class="pill">${html(state)}</span></div>
    <p class="muted"><strong>Provenance</strong> · ${html(sourceLabel(item))} · ${html(sourceDetail(item))}</p>
    <p class="muted">Provider ${html(item.provider_key||"unknown")} · proposal ${html(item.id)} · revision ${html(item.revision||1)}</p>
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
