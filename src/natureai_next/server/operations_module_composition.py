"""Composition-time ownership for the nested Operations browser projections."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LEGACY_OPERATIONS_RELATED_PROJECT_START = (
    b' const operations=q("operations-list");\n if(operations){\n  const oldOperationsClick=operations.onclick;'
)
_LEGACY_OPERATIONS_RELATED_PROJECT_END = (
    b'\n document.querySelectorAll(".nav[data-page]").forEach'
)
_LEGACY_OPERATIONS_DOMAIN_TAB_GROUP = (
    b'["media-filter","observation-filter","research-domain","operations-domain"]'
)
_APPLICATION_OWNED_TAB_GROUPS = (
    b'["media-filter","observation-filter","research-domain"]'
)

_OPERATIONS_RELATED_PROJECT_PATCH = bytes(
    r"""

/* WEB-OPERATIONS-RELATED-PROJECT: Operations-owned related-project affordance. */
(()=>{
 if(window.__fieldoraOperationsRelatedProjectWired)return;
 window.__fieldoraOperationsRelatedProjectWired=true;
 const moduleId="operations";
 const ownedDomains=new Set(["assets","maintenance","calibrations","documents"]);
 let host=null,unsubscribe=null;
 const contracts=()=>window.FieldoraModuleContracts;
 const currentHost=()=>contracts()?.resolve("operations.workspace.host")||null;
 const projectContext=()=>contracts()?.resolve("projects.context.select")||null;
 const navigation=()=>contracts()?.resolve("navigation.navigate")||null;
 const detail=()=>document.getElementById("operations-detail");
 const clear=()=>detail()?.querySelector("[data-open-related-project]")?.remove();
 const installHost=()=>{
  const next=currentHost();if(!next)return false;
  if(host===next)return true;
  if(unsubscribe)unsubscribe();
  host=next;
  unsubscribe=typeof host.subscribe==="function"?host.subscribe(clear):null;
  return true;
 };
 const openProject=projectId=>{
  const context=projectContext(),navigator=navigation();
  if(!context?.select||!navigator?.navigate)return false;
  if(context.select(projectId)===false)return false;
  navigator.navigate("/projects",moduleId,"push");
  return true;
 };
 const onRecordClick=event=>{
  if(!installHost()||!ownedDomains.has(String(host.currentDomain?.()||""))){clear();return}
  const row=event.target.closest?.("[data-operations-id]");if(!row)return;
  const item=(host.records?.()||[]).find(record=>String(record?.id)===String(row.dataset.operationsId));
  clear();
  if(!item?.project_id||!projectContext()?.select||!navigation()?.navigate)return;
  const target=detail();if(!target)return;
  const button=document.createElement("button");button.className="primary section";
  button.dataset.openRelatedProject="true";button.textContent="Open related project";
  button.onclick=()=>openProject(item.project_id);
  target.appendChild(button);
 };
 document.getElementById("operations-list")?.addEventListener("click",onRecordClick);
 if(!installHost())document.addEventListener("fieldora:contracts-ready",installHost,{once:true});
})();
""",
    "utf-8",
)

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
 const recoverOperationsDomain=()=>{
  const host=window.FieldoraModuleContracts?.resolve("operations.workspace.host");
  if(!host)return false;
  if(["assets","maintenance","calibrations","documents"].includes(host.currentDomain())){
   void host.selectDomain("locations");
  }
  return true;
 };
 if(!recoverOperationsDomain()){
  document.addEventListener("fieldora:contracts-ready",recoverOperationsDomain,{once:true});
 }
 const indicator=document.getElementById("operations-view-indicator");
 if(indicator)indicator.textContent="Locations view";
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
 const redirectFromRemovedOperations=()=>{
  if(
   location.hash!=="#operations"||
   !document.getElementById("page-administration")
  )return true;
  const navigation=window.FieldoraModuleContracts?.resolve("navigation.navigate");
  if(!navigation)return false;
  navigation.navigate("/administration","operations","replace");
  return true;
 };
 if(!redirectFromRemovedOperations()){
  document.addEventListener(
   "fieldora:contracts-ready",
   redirectFromRemovedOperations,
   {once:true}
  );
 }
})();
""",
    "utf-8",
)


def _strip_legacy_related_project_wiring(body: bytes) -> bytes:
    start = body.find(_LEGACY_OPERATIONS_RELATED_PROJECT_START)
    if start < 0:
        return body
    end = body.find(_LEGACY_OPERATIONS_RELATED_PROJECT_END, start)
    if end < 0:
        return body
    return body[:start] + body[end:]


def _strip_legacy_operations_domain_tab_wiring(body: bytes) -> bytes:
    return body.replace(
        _LEGACY_OPERATIONS_DOMAIN_TAB_GROUP,
        _APPLICATION_OWNED_TAB_GROUPS,
    )


def compose_operations_browser_response(target: str, response: ApiResponse) -> ApiResponse:
    """Replace legacy cross-screen wiring with the Operations-owned adapter."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = _strip_legacy_operations_domain_tab_wiring(response.body)
    body = _strip_legacy_related_project_wiring(body)
    if _OPERATIONS_RELATED_PROJECT_PATCH not in body:
        body += _OPERATIONS_RELATED_PROJECT_PATCH
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)


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
    body = _strip_legacy_operations_domain_tab_wiring(response.body)
    body = _strip_legacy_related_project_wiring(body)
    if patch not in body:
        body += patch
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)
