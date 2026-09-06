"""Projects-owned browser service for governed Project evidence access."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_EVIDENCE_SERVICE_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-EVIDENCE-SERVICE-PROVIDER: governed Project evidence service. */
(()=>{
 if(window.__fieldoraProjectEvidenceServiceProviderWired)return;window.__fieldoraProjectEvidenceServiceProviderWired=true;
 const moduleId="projects.core",contractName="projects.evidence.service";
 const freezeItems=items=>Object.freeze((Array.isArray(items)?items:[]).map(item=>Object.freeze({...item})));
 async function projectItems(projectId){
  const id=String(projectId||"").trim();if(!id)return Object.freeze([]);
  const result=await api(`/api/v1/media?project_id=${encodeURIComponent(id)}&limit=200`,{purpose:"research"});
  return freezeItems(result?.items);
 }
 async function libraryItems(){
  const result=await api("/api/v1/media?limit=200",{purpose:"research"});
  return freezeItems(result?.items);
 }
 async function link(projectId,mediaId){
  const pid=String(projectId||"").trim(),mid=String(mediaId||"").trim();
  if(!pid||!mid)throw new Error("Project and evidence identifiers are required.");
  const result=await api(`/api/v1/projects/${encodeURIComponent(pid)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mid})});
  return result?.item?Object.freeze({...result.item}):null;
 }
 const implementation=Object.freeze({projectItems,libraryItems,link});
 function register(){
  const contracts=window.FieldoraModuleContracts;if(!contracts)return false;
  const current=contracts.resolve(contractName);if(current)return current===implementation;
  contracts.register(contractName,moduleId,implementation);return true;
 }
 register();document.addEventListener('fieldora:contracts-ready',register,{once:true});
})();
""",
    "utf-8",
)


def patch_project_evidence_service_provider_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Project evidence provider after the contract runtime."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _PROJECT_EVIDENCE_SERVICE_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_EVIDENCE_SERVICE_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
