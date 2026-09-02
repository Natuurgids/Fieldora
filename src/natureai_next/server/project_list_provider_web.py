"""Projects-owned browser provider for accessible project-list state."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_LIST_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-LIST-PROVIDER: Projects-owned accessible project snapshots. */
(()=>{
 if(window.__fieldoraProjectListProviderWired)return;window.__fieldoraProjectListProviderWired=true;
 const moduleId="projects.core",contractName="projects.list.read";
 const state={items:[]};
 const snapshot=()=>Object.freeze(state.items.map(item=>Object.freeze({...item})));
 async function refresh(){
  const result=await api('/api/v1/projects',{purpose:'research'});
  state.items=Array.isArray(result?.items)?result.items.map(item=>({...item})):[];
  const items=snapshot();
  document.dispatchEvent(new CustomEvent('fieldora:project-list-changed',{detail:{module_id:moduleId,count:items.length}}));
  return items;
 }
 const implementation=Object.freeze({items:snapshot,refresh});
 function register(){
  const contracts=window.FieldoraModuleContracts;if(!contracts)return false;
  const current=contracts.resolve(contractName);
  if(current)return current===implementation;
  contracts.register(contractName,moduleId,implementation);return true;
 }
 register();
 document.addEventListener('fieldora:contracts-ready',register,{once:true});
 window.FieldoraProjectList=Object.freeze({items:snapshot,refresh});
})();
""",
    "utf-8",
)


def patch_project_list_provider_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Projects list provider only after the contract runtime exists."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _PROJECT_LIST_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_LIST_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
