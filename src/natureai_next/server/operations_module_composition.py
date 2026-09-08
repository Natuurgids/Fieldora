"""Composition-time suppression for the nested Operations browser projections."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_OPERATIONS_WITH_FACILITIES_PATCH = bytes(
    r"""

/* WEB-OPERATIONS-BASE-OMISSION:FACILITIES */
(()=>{
 const page=document.getElementById("page-operations");
 if(!page)return;
 ["assets","maintenance","calibrations"].forEach(domain=>{
  page.querySelectorAll(`[data-operations-domain="${domain}"]`).forEach(
   node=>node.remove()
  );
 });
 const heading=page.querySelector(".top h1");
 if(heading)heading.textContent="Facilities";
 document.querySelectorAll('[data-workspace-target="operations"]').forEach(button=>{
  button.textContent="Facilities";
 });
 document.querySelectorAll('.nav[data-page="operations"]').forEach(button=>{
  button.innerHTML='<span class="nav-icon">⌂</span>Facilities';
 });
 let switched=false;
 if(
  typeof operationsDomain!=="undefined"&&
  ["assets","maintenance","calibrations","documents"].includes(operationsDomain)
 ){
  operationsDomain="locations";
  switched=true;
 }
 const indicator=document.getElementById("operations-view-indicator");
 if(indicator)indicator.textContent="Locations view";
 if(switched&&!page.hidden&&typeof loadOperations==="function")loadOperations();
})();
""",
    "utf-8",
)

_OPERATIONS_WITHOUT_FACILITIES_PATCH = bytes(
    r"""

/* WEB-OPERATIONS-BASE-OMISSION:EMPTY */
(()=>{
 const page=document.getElementById("page-operations");
 if(page)page.remove();
 document.querySelectorAll('.nav[data-page="operations"]').forEach(node=>node.remove());
 document.querySelectorAll('[data-workspace-target="operations"]').forEach(
  node=>node.remove()
 );
 if(
  location.hash==="#operations"&&
  document.getElementById("page-administration")&&
  typeof showPage==="function"
 )showPage("administration");
})();
""",
    "utf-8",
)


def suppress_operations_browser_response(
    target: str,
    response: ApiResponse,
    *,
    facilities_composed: bool,
) -> ApiResponse:
    """Remove Operations-owned browser controls while preserving Facilities."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    patch = (
        _OPERATIONS_WITH_FACILITIES_PATCH
        if facilities_composed
        else _OPERATIONS_WITHOUT_FACILITIES_PATCH
    )
    if patch in response.body:
        return response
    return ApiResponse(
        response.status,
        response.body + patch,
        response.content_type,
        response.headers,
    )
