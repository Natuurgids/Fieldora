"""Deterministic AI Administration zero-trust action reconciliation."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_AIADMIN_ZERO_TRUST_RECONCILIATION_PATCH = br"""

/* Reconcile AI Administration action visibility synchronously on page entry and load. */
(()=>{
 if(window.__fieldoraAiAdminZeroTrustReconciliation)return;
 window.__fieldoraAiAdminZeroTrustReconciliation=true;
 const reconcile=()=>{
  const select=document.getElementById('ai-record-type');
  if(!select||document.body.dataset.fieldoraCapabilities!=='ready')return;
  select.dispatchEvent(new Event('change'));
 };
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
 reconcile();
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
