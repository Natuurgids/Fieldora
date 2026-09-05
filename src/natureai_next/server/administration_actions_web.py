"""WEB-045 Administration browser action authorization alignment."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ADMINISTRATION_ACTIONS_PATCH = br"""

/* WEB-045 Administration exact, resource-scoped action authorization. */
(()=>{
 if(window.__fieldoraAdministrationActions)return;
 window.__fieldoraAdministrationActions=true;
 const mark=(node,hidden)=>{if(node)node.dataset.fieldoraAuthorizationHidden=hidden?"true":"false"};
 const serviceActions=new Map(),archiveActions=new Map();
 function protectUnverified(){
  document.querySelectorAll('#page-operator [data-op]').forEach(button=>{
   if(button.dataset.administrationActionVerified!=="true")mark(button,true);
  });
  document.querySelectorAll('#page-operator [data-linked-archive-action]').forEach(button=>{
   if(button.dataset.administrationActionVerified!=="true")mark(button,true);
  });
 }
 function apply(){
  protectUnverified();
  document.querySelectorAll('#page-operator [data-op][data-service]').forEach(button=>{
   const allowed=serviceActions.get(button.dataset.service);
   if(!allowed)return;
   button.dataset.administrationActionVerified="true";
   mark(button,!allowed.has(button.dataset.op));
  });
  document.querySelectorAll('#page-operator [data-linked-archive-action][data-linked-storage-id]').forEach(button=>{
   const allowed=archiveActions.get(button.dataset.linkedStorageId);
   if(!allowed)return;
   button.dataset.administrationActionVerified="true";
   mark(button,!allowed.has(button.dataset.linkedArchiveAction));
  });
 }
 function rememberOverview(payload){
  (payload.services||[]).forEach(item=>{
   if(item.service_id)serviceActions.set(String(item.service_id),new Set(item.allowed_actions||[]));
  });
  (payload.linked_archives||[]).forEach(item=>{
   if(item.storage_id)archiveActions.set(String(item.storage_id),new Set(item.allowed_actions||[]));
  });
  queueMicrotask(apply);
 }
 const baseApi=api;
 api=async function(path,options={}){
  const result=await baseApi(path,options);
  if(String(path||'').split('?',1)[0]==='/api/v1/operator/overview'&&result)rememberOverview(result);
  return result;
 };
 const observer=new MutationObserver(()=>{protectUnverified();apply()});
 observer.observe(document.body,{childList:true,subtree:true});
 document.querySelectorAll('.nav[data-page="operator"],[data-workspace-target="operator"]').forEach(button=>{
  button.addEventListener('click',protectUnverified);
 });
 protectUnverified();
})();
"""


def patch_administration_actions_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append WEB-045 exact Administration action filtering to app.js."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _ADMINISTRATION_ACTIONS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _ADMINISTRATION_ACTIONS_PATCH,
        response.content_type,
        response.headers,
    )
