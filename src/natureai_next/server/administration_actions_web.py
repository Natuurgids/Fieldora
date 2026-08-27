"""WEB-045 Administration browser action authorization alignment."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ADMINISTRATION_ACTIONS_PATCH = br"""

/* WEB-045 Administration exact-action authorization. */
(()=>{
 if(window.__fieldoraAdministrationActions)return;
 window.__fieldoraAdministrationActions=true;
 const serviceAction={
  activate:"operator.services.activate",
  drain:"operator.services.drain",
  stop:"operator.services.stop",
  revoke:"operator.services.revoke"
 };
 const archiveAction={
  enable:"operator.storage.enable",
  disable:"operator.storage.disable"
 };
 let actionCapabilities=null,loading=null;
 const mark=(node,hidden)=>{if(node)node.dataset.fieldoraAuthorizationHidden=hidden?"true":"false"};
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
  if(!actionCapabilities)return;
  document.querySelectorAll('#page-operator [data-op]').forEach(button=>{
   const key=serviceAction[button.dataset.op];
   button.dataset.administrationActionVerified="true";
   mark(button,!key||actionCapabilities[key]!==true);
  });
  document.querySelectorAll('#page-operator [data-linked-archive-action]').forEach(button=>{
   const key=archiveAction[button.dataset.linkedArchiveAction];
   button.dataset.administrationActionVerified="true";
   mark(button,!key||actionCapabilities[key]!==true);
  });
 }
 async function refresh(){
  if(loading)return loading;
  loading=(async()=>{
   try{
    const payload=await api('/api/v1/web/capabilities',{purpose:'administration'});
    actionCapabilities=payload.actions||{};
   }catch(_error){actionCapabilities={}}
   finally{loading=null;apply()}
  })();
  return loading;
 }
 const observer=new MutationObserver(()=>{protectUnverified();if(actionCapabilities)apply()});
 observer.observe(document.body,{childList:true,subtree:true});
 document.querySelectorAll('.nav[data-page="operator"],[data-workspace-target="operator"]').forEach(button=>{
  button.addEventListener('click',()=>{protectUnverified();refresh()});
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
