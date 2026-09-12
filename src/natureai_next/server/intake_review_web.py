"""Browser wiring from governed submissions through review determinations."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_INTAKE_REVIEW_WEB_PATCH = bytes(
    r"""

/* Fieldora intake -> review -> determination continuity. */
(()=>{
 if(window.__fieldoraIntakeReviewWired)return;
 window.__fieldoraIntakeReviewWired=true;
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const reviewPage=byId("page-intake-review");
 if(!reviewPage)return;

 function prepareReviewFromSubmission(row){
  const submissionId=row.dataset.submissionId||row.querySelector("[data-submission-id]")?.dataset.submissionId||"";
  const project=row.dataset.projectId||"";
  if(!submissionId)return;
  byId("review-subject-type").value="submission";
  byId("review-subject").value=submissionId;
  byId("review-project").value=project;
  byId("review-domain").focus();
  byId("collab-status").textContent=`Submission ${submissionId} selected for expert review.`;
 }

 function renderSubmissions(items){
  const list=byId("platform-submissions");if(!list)return;
  list.innerHTML=items.length?items.map(item=>{
   const project=item.project_id||"";
   return `<div class="row" data-submission-id="${html(item.submission_id)}" data-project-id="${html(project)}"><strong>${html(item.source_type||"submission")}</strong><span>${html(project||"General Library")}</span><span class="pill">${html(item.state||"registered")}</span><span data-submission-id="${html(item.submission_id)}">${html(item.submission_id)}</span></div>`;
  }).join(""):'<div class="empty">No governed submissions in your access scope.</div>';
  enhanceSubmissionRows();
 }

 async function loadReviewCase(reviewCaseId){
  if(!reviewCaseId)return;
  byId("review-case-id").value=reviewCaseId;
  try{
   const result=await api(`/api/v1/review-cases/${encodeURIComponent(reviewCaseId)}`),detail=byId("review-detail"),item=result.review_case||{},determinations=result.determinations||[];
   detail.innerHTML=`<p><strong>${html(item.domain||"Review")}</strong> · <span class="pill">${html(item.state||"")}</span></p>`+determinations.map(d=>`<div class="row" data-determination-id="${html(d.determination_id)}"><strong>${html(d.assertion)}</strong><span>${Math.round(Number(d.confidence||0)*100)}%</span><span>${html(d.expert_id||"")}</span><span>${html(d.determination_id)}</span></div>`).join("");
   enhanceDeterminations();
  }catch(error){byId("review-detail").textContent=error.message||String(error)}
 }

 function renderReviews(items){
  const list=byId("platform-reviews");if(!list)return;
  list.innerHTML=items.length?items.map(item=>`<button type="button" class="row review-row" data-review-case-id="${html(item.review_case_id)}"><strong>${html(item.domain||"Review")}</strong><span>${html(item.specialty||"General")}</span><span class="pill">${html(item.state||"")}</span><span>${html(item.subject_id||"")}</span></button>`).join(""):'<div class="empty">No expert review cases in your access scope.</div>';
  list.querySelectorAll("[data-review-case-id]").forEach(row=>row.addEventListener("click",()=>loadReviewCase(row.dataset.reviewCaseId)));
 }

 async function refreshIntakeReview(){
  const status=byId("collab-status");
  try{
   const [submissions,reviews]=await Promise.all([api("/api/v1/submissions?limit=100"),api("/api/v1/review-cases?limit=100")]);
   renderSubmissions(submissions.items||[]);renderReviews(reviews.items||[]);
   if(status)status.textContent=`${submissions.count??(submissions.items||[]).length} submissions · ${reviews.count??(reviews.items||[]).length} review cases`;
  }catch(error){if(status)status.textContent=error.message||String(error)}
 }

 function enhanceSubmissionRows(){
  const list=byId("platform-submissions");if(!list)return;
  list.querySelectorAll(":scope > .row").forEach(row=>{
   if(row.dataset.reviewWired)return;
   row.dataset.reviewWired="true";
   if(!row.dataset.submissionId){
    const spans=[...row.querySelectorAll(":scope > span")];
    row.dataset.projectId=(spans[0]?.textContent||"").trim()==="General Library"?"":(spans[0]?.textContent||"").trim();
    row.dataset.submissionId=(spans.at(-1)?.textContent||"").trim();
   }
   row.tabIndex=0;row.setAttribute("role","button");
   row.title="Select this governed submission for expert review";
   const action=document.createElement("button");
   action.type="button";action.textContent="Request review";action.className="primary";
   action.addEventListener("click",event=>{event.stopPropagation();prepareReviewFromSubmission(row)});
   row.appendChild(action);
   row.addEventListener("dblclick",()=>prepareReviewFromSubmission(row));
   row.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();prepareReviewFromSubmission(row)}});
  });
 }

 function enhanceDeterminations(){
  const detail=byId("review-detail");if(!detail)return;
  detail.querySelectorAll(":scope > .row").forEach(row=>{
   if(row.dataset.acceptWired)return;
   row.dataset.acceptWired="true";
   const spans=[...row.querySelectorAll(":scope > span")],determinationId=row.dataset.determinationId||(spans.at(-1)?.textContent||"").trim();
   if(!determinationId)return;
   const action=document.createElement("button");
   action.type="button";action.textContent="Accept determination";
   action.addEventListener("click",()=>{
    byId("review-accept-id").value=determinationId;
    byId("review-accept").click();
   });
   row.appendChild(action);
  });
 }

 const top=reviewPage.querySelector(".top");
 if(top&&!byId("intake-review-refresh")){
  const refresh=document.createElement("button");refresh.type="button";refresh.id="intake-review-refresh";refresh.textContent="Refresh";refresh.addEventListener("click",refreshIntakeReview);top.appendChild(refresh);
 }
 document.querySelectorAll('[data-workspace-target="intake-review"],.nav[data-page="intake-review"]').forEach(button=>button.addEventListener("click",()=>setTimeout(refreshIntakeReview,0)));
 ["submission-create","review-create","review-determine","review-accept"].forEach(id=>byId(id)?.addEventListener("click",()=>setTimeout(refreshIntakeReview,250)));
 const observer=new MutationObserver(()=>{enhanceSubmissionRows();enhanceDeterminations()});
 observer.observe(reviewPage,{childList:true,subtree:true});
 enhanceSubmissionRows();enhanceDeterminations();
 if(!reviewPage.hidden)refreshIntakeReview();
})();
""",
    "utf-8",
)


def patch_intake_review_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append review-continuity behavior only to the managed browser app bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _INTAKE_REVIEW_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _INTAKE_REVIEW_WEB_PATCH,
        response.content_type,
        response.headers,
    )
