"""WEB-044 Facilities/Operations browser action alignment."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_FACILITY_ACTIONS_PATCH = br"""

/* WEB-044 Facilities/Operations governed movement actions. */
(()=>{
 if(window.__fieldoraFacilityActions)return;
 window.__fieldoraFacilityActions=true;
 const q=id=>document.getElementById(id);
 function status(message){const host=q("facility-planning-status");if(host)host.textContent=message}
 async function governRow(row){
  const buttons=[...row.querySelectorAll("button[data-step][data-state]")];
  if(!buttons.length||row.dataset.facilityActionsLoading==="1")return;
  row.dataset.facilityActionsLoading="1";
  buttons.forEach(button=>{button.disabled=true;button.hidden=true});
  const stepId=buttons[0].dataset.step;
  try{
   const result=await api(`/api/v1/facility-planning/steps/${encodeURIComponent(stepId)}`,{purpose:"operations"});
   const step=result.step||{},allowed=new Set(step.next_actions||[]);
   buttons.forEach(button=>{
    const permitted=allowed.has(button.dataset.state);
    button.hidden=!permitted;
    button.disabled=!permitted;
    if(permitted)button.dataset.facilityMovementAction="true";
   });
   const pill=row.querySelector(".pill");
   if(step.is_terminal&&pill&&!row.querySelector("[data-facility-terminal]")){
    const note=document.createElement("small");
    note.dataset.facilityTerminal="true";
    note.className="muted";
    note.textContent=" No further movement action is permitted.";
    pill.after(note);
   }
  }catch(error){status(`Movement actions unavailable: ${error.message}`)}
  finally{delete row.dataset.facilityActionsLoading}
 }
 function governCampaign(){
  const host=q("facility-campaign-detail");if(!host)return;
  host.querySelectorAll(".row").forEach(governRow);
  if(!host.dataset.facilityPicklist){
   host.dataset.facilityPicklist="true";
   const heading=document.createElement("p");
   heading.className="muted";
   heading.textContent="Execution picklist: current placement remains authoritative until a permitted final placement action is recorded.";
   host.prepend(heading);
  }
 }
 const observer=new MutationObserver(governCampaign);
 function attach(){const host=q("facility-campaign-detail");if(!host)return;observer.observe(host,{childList:true,subtree:true});governCampaign()}
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",attach,{once:true});else attach();
 document.querySelectorAll('.nav[data-page="operations"]').forEach(button=>button.addEventListener("click",()=>queueMicrotask(attach)));
})();
"""


def patch_facility_actions_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the WEB-044 browser action contract once to app.js."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _FACILITY_ACTIONS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _FACILITY_ACTIONS_PATCH,
        response.content_type,
        response.headers,
    )
