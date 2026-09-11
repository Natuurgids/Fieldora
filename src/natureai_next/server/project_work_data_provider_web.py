"""Projects-owned browser service for governed Project work data."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_WORK_DATA_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-WORK-DATA-PROVIDER: governed Project work-data service. */
(()=>{
 if(window.__fieldoraProjectWorkDataProviderWired)return;window.__fieldoraProjectWorkDataProviderWired=true;
 const moduleId="projects.core",contractName="projects.work-data.service";
 const freezeItems=items=>Object.freeze((Array.isArray(items)?items:[]).map(item=>Object.freeze({...item})));
 const projectId=value=>String(value||"").trim();
 async function load(value){
  const id=projectId(value);if(!id)return Object.freeze({phases:Object.freeze([]),tasks:Object.freeze([]),sprints:Object.freeze([]),allocations:Object.freeze([])});
  const pid=encodeURIComponent(id);
  const [phases,tasks,sprints,allocations]=await Promise.all([
   api(`/api/v1/phases?project_id=${pid}`,{purpose:"research"}),
   api(`/api/v1/tasks?project_id=${pid}`,{purpose:"research"}),
   api(`/api/v1/sprints?project_id=${pid}`,{purpose:"research"}),
   api(`/api/v1/allocations?project_id=${pid}`,{purpose:"research"})
  ]);
  return Object.freeze({phases:freezeItems(phases?.items),tasks:freezeItems(tasks?.items),sprints:freezeItems(sprints?.items),allocations:freezeItems(allocations?.items)});
 }
 async function statuses(value){
  const id=projectId(value);if(!id)return Object.freeze([]);
  const result=await api(`/api/v1/project-statuses?project_id=${encodeURIComponent(id)}`,{purpose:"research"});
  return freezeItems(result?.items);
 }
 async function create(kind,record){
  const name=String(kind||"").trim();
  const path=name==="phase"?"/api/v1/phases":(name==="task"||name==="milestone"||name==="subtask")?"/api/v1/tasks":name==="sprint"?"/api/v1/sprints":name==="allocation"?"/api/v1/allocations":"";
  if(!path)throw new Error(`Unsupported Project work kind: ${name}`);
  const result=await api(path,{method:"POST",purpose:"research",body:JSON.stringify({...record})});
  return result?.item?Object.freeze({...result.item}):null;
 }
 const implementation=Object.freeze({load,statuses,create});
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


def patch_project_work_data_provider_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Project work-data provider after the contract runtime."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _PROJECT_WORK_DATA_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_WORK_DATA_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
