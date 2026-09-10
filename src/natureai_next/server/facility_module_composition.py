"""Composition-time suppression for the nested Facilities browser projections."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_web import _FACILITY_ACTIONS_PATCH
from natureai_next.server.facility_web_compatibility import (
    _FACILITY_PLANNING_SERVICE_PROVIDER_PATCH,
    _FACILITY_WEB_PATCH,
)
from natureai_next.server.offline_maps_web import (
    _OFFLINE_MAPS_SERVICE_PROVIDER_PATCH,
    _OFFLINE_MAPS_WEB_PATCH,
)
from natureai_next.server.project_facility_workspace_web import (
    _PROJECT_FACILITY_WORKSPACE_PATCH,
)

_FACILITY_BASE_OMISSION_PATCH = r"""

/* WEB-FACILITIES-BASE-OMISSION: remove legacy Facilities controls. */
(()=>{
 const page=document.getElementById("page-operations");
 if(!page)return;
 ["locations","drawings"].forEach(domain=>{
  page.querySelectorAll(`[data-operations-domain="${domain}"]`).forEach(
   node=>node.remove()
  );
 });
 const heading=page.querySelector(".top h1");
 if(heading)heading.textContent="Asset & Equipment Operations";
 document.querySelectorAll('[data-workspace-target="operations"]').forEach(button=>{
  button.textContent="Asset & Equipment Operations";
 });
 document.querySelectorAll('.nav[data-page="operations"]').forEach(button=>{
  button.innerHTML='<span class="nav-icon">⌂</span>Asset & Equipment Operations';
 });
 const recoverFacilitiesDomain=()=>{
  const host=window.FieldoraModuleContracts?.resolve("operations.workspace.host");
  if(!host)return false;
  if(["locations","drawings"].includes(host.currentDomain()))void host.selectDomain("assets");
  return true;
 };
 if(!recoverFacilitiesDomain()){
  document.addEventListener("fieldora:contracts-ready",recoverFacilitiesDomain,{once:true});
 }
})();
""".encode()


def suppress_facilities_browser_response(target: str, response: ApiResponse) -> ApiResponse:
    """Remove Facilities-owned browser code when that extension is not composed."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response

    body = (
        response.body.replace(_FACILITY_ACTIONS_PATCH, b"")
        .replace(_FACILITY_PLANNING_SERVICE_PROVIDER_PATCH, b"")
        .replace(_FACILITY_WEB_PATCH, b"")
        .replace(_OFFLINE_MAPS_SERVICE_PROVIDER_PATCH, b"")
        .replace(_OFFLINE_MAPS_WEB_PATCH, b"")
        .replace(_PROJECT_FACILITY_WORKSPACE_PATCH, b"")
    )
    if _FACILITY_BASE_OMISSION_PATCH not in body:
        body += _FACILITY_BASE_OMISSION_PATCH

    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)
