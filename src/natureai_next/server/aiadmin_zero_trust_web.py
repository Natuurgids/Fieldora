"""Deterministic AI Administration zero-trust action reconciliation."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_AIADMIN_ZERO_TRUST_RECONCILIATION_PATCH = br"""

/* Preserve the authoritative AI Administration option projection after bootstrap. */
(()=>{
 if(window.__fieldoraAiAdminZeroTrustReconciliation)return;
 window.__fieldoraAiAdminZeroTrustReconciliation=true;
 const denied=new Set();
 let captured=false;
 const select=()=>document.getElementById('ai-record-type');
 function capture(){
  const node=select();
  if(captured||!node||document.body.dataset.fieldoraCapabilities!=='ready')return;
  [...node.options].forEach(option=>{if(option.disabled)denied.add(option.value)});
  captured=true;
 }
 function reconcile(){
  capture();
  const node=select();if(!captured||!node)return;
  [...node.options].forEach(option=>{
   if(!denied.has(option.value))return;
   if(!option.disabled)option.disabled=true;
   if(!option.hidden)option.hidden=true;
  });
  const available=[...node.options].filter(option=>!option.disabled);
  if(node.selectedOptions[0]?.disabled&&available[0])node.value=available[0].value;
  const save=document.getElementById('ai-record-save');
  if(save){
   const hidden=available.length===0||denied.has(node.value)?'true':'false';
   if(save.dataset.fieldoraAuthorizationHidden!==hidden)save.dataset.fieldoraAuthorizationHidden=hidden;
  }
 }
 const readiness=new MutationObserver(()=>{capture();reconcile()});
 readiness.observe(document.body,{attributes:true,attributeFilter:['data-fieldora-capabilities']});
 const baseShowPage=showPage;
 showPage=function(page){
  baseShowPage(page);
  if(page==='aiadmin')reconcile();
 };
 const baseLoadAIAdministration=loadAIAdministration;
 loadAIAdministration=async function(){
  try{return await baseLoadAIAdministration();}
  finally{reconcile();}
 };
 const optionObserver=new MutationObserver(()=>reconcile());
 const aiSelect=select();if(aiSelect)optionObserver.observe(aiSelect,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','hidden']});
 queueMicrotask(()=>{capture();reconcile()});
})();
"""


def patch_aiadmin_zero_trust_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append deterministic AI Administration action reconciliation to app.js."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _AIADMIN_ZERO_TRUST_RECONCILIATION_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _AIADMIN_ZERO_TRUST_RECONCILIATION_PATCH,
        response.content_type,
        response.headers,
    )
