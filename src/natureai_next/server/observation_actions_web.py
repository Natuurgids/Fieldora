"""Final Observation action labels for WEB-041 browser parity."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_OBSERVATION_ACTIONS_PATCH = bytes(
    r"""

/* WEB-041: visible Observation controls use the governed confirmation states. */
(()=>{
 if(window.__fieldoraObservationActionsWired)return;
 window.__fieldoraObservationActionsWired=true;
 const rejected=document.querySelector('[data-observation-filter="disputed"]');
 if(rejected){rejected.dataset.observationFilter="rejected";rejected.textContent="Rejected";}
 const returnToReview=document.querySelector('[data-observation-decision="deferred"]');
 if(returnToReview){
  returnToReview.dataset.observationDecision="unconfirmed";
  returnToReview.textContent="Return to review";
 }
})();
""",
    "utf-8",
)


def patch_observation_actions_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _OBSERVATION_ACTIONS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _OBSERVATION_ACTIONS_PATCH,
        response.content_type,
        response.headers,
    )
