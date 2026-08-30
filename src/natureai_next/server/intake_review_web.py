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
 const reviewPage=byId("page-intake-review");
 if(!reviewPage)return;

 function prepareReviewFromSubmission(row){
  const spans=[...row.querySelectorAll(":scope > span")];
  const project=(spans[0]?.textContent||"").trim();
  const submissionId=(spans.at(-1)?.textContent||"").trim();
  if(!submissionId)return;
  byId("review-subject-type").value="submission";
  byId("review-subject").value=submissionId;
  byId("review-project").value=project==="General Library"?"":project;
  byId("review-domain").focus();
  byId("collab-status").textContent=`Submission ${submissionId} selected for expert review.`;
 }

 function enhanceSubmissionRows(){
  const list=byId("platform-submissions");if(!list)return;
  list.querySelectorAll(":scope > .row").forEach(row=>{
   if(row.dataset.reviewWired)return;
   row.dataset.reviewWired="true";
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
   const spans=[...row.querySelectorAll(":scope > span")],determinationId=(spans.at(-1)?.textContent||"").trim();
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

 const observer=new MutationObserver(()=>{enhanceSubmissionRows();enhanceDeterminations()});
 observer.observe(reviewPage,{childList:true,subtree:true});
 enhanceSubmissionRows();enhanceDeterminations();
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
