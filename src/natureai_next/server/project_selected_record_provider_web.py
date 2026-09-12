"""Projects-owned selected-record contract for replaceable inspector consumers."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_SELECTED_RECORD_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-SELECTED-RECORD-PROVIDER: Projects-owned selected-record state. */
(()=>{
 if(window.__fieldoraProjectSelectedRecordProviderWired)return;window.__fieldoraProjectSelectedRecordProviderWired=true;
 const moduleId="projects.core",contractName="projects.selected-record.select";
 const state={selection:null};
 function normalize(value){
  if(!value)return null;
  const record=value.record&&typeof value.record==="object"?Object.freeze({...value.record}):null;
  const kind=String(value.kind||"").trim(),id=String(value.id||record?.id||"").trim();
  if(!kind||!id||!record)throw new Error("Selected Project record requires kind, id and record.");
  return Object.freeze({kind,id,record});
 }
 function same(left,right){return left===right||Boolean(left&&right&&left.kind===right.kind&&left.id===right.id&&JSON.stringify(left.record)===JSON.stringify(right.record))}
 function publish(){document.dispatchEvent(new CustomEvent("fieldora:project-selected-record-changed",{detail:{module_id:moduleId,selection:state.selection}}))}
 function select(value){const next=normalize(value);if(same(state.selection,next))return true;state.selection=next;publish();return true}
 const implementation=Object.freeze({select,current:()=>state.selection});
 function register(){
  const contracts=window.FieldoraModuleContracts;if(!contracts||contracts.provider?.(contractName)!==moduleId)return false;
  const current=contracts.resolve(contractName);if(current)return current===implementation;
  contracts.register(contractName,moduleId,implementation);return true;
 }
 register();
 document.addEventListener("fieldora:contracts-ready",register,{once:true});
})();
""",
    "utf-8",
)


def patch_project_selected_record_provider_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the selected-record provider after the contract runtime."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _SELECTED_RECORD_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _SELECTED_RECORD_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
