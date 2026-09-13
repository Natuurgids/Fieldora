"""Managed-web trust view for FieldoraBastion-backed secure acquisition."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_SECURE_ACQUISITION_WEB_PATCH = bytes(
    r"""

/* Fieldora secure acquisition: trusted-side Bastion acceptance visibility. */
(()=>{
 if(window.__fieldoraSecureAcquisitionWired)return;window.__fieldoraSecureAcquisitionWired=true;
 const page=document.getElementById("page-operations");if(!page)return;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const section=document.createElement("section");section.id="secure-acquisition";section.className="card section";
 section.innerHTML=`<h2>Secure acquisition</h2><p class="muted">External packages are quarantined and scanned by FieldoraBastion before trusted-side acceptance. Fieldora independently verifies signed manifests, clean-scan claims, and payload digests. The browser cannot mark content clean or bypass acceptance policy.</p><div id="secure-acquisition-summary" class="list"></div><p id="secure-acquisition-status" class="status"></p>`;
 const maps=document.getElementById("offline-map-packages");if(maps)maps.insertAdjacentElement("beforebegin",section);else page.appendChild(section);
 const trust=item=>item?.manifest_signature==="ed25519"&&item?.malware_scan?.result==="clean"?"Signed + clean scanned":item?.manifest_signature==="ed25519"?"Signed manifest":"Local/unattested";
 async function accepted(){
  const [models,maps]=await Promise.all([
   api("/api/v1/models/installed",{purpose:"administration"}).catch(()=>({items:[]})),
   api("/api/v1/maps/installed",{purpose:"administration"}).catch(()=>({items:[]})),
  ]);
  return [
   ...(Array.isArray(models?.items)?models.items:[]).map(item=>({kind:"AI model",name:item.name||item.model_id||"Model",trust:trust(item)})),
   ...(Array.isArray(maps?.items)?maps.items:[]).map(item=>({kind:"Offline map",name:item.name||item.map_id||"Map",trust:trust(item)})),
  ];
 }
 async function load(){const list=document.getElementById("secure-acquisition-summary"),state=document.getElementById("secure-acquisition-status");if(!list)return;try{const items=await accepted();list.innerHTML=items.map(item=>`<div class="row"><div><strong>${esc(item.name)}</strong><br><span class="muted">${esc(item.kind)}</span></div><span class="pill">${esc(item.trust)}</span></div>`).join("")||'<div class="empty">No Bastion/air-gap packages have been accepted into trusted storage.</div>';if(state)state.textContent="Quarantine and scanner state remains authoritative in FieldoraBastion; only accepted trust metadata is shown here."}catch(error){list.innerHTML='<div class="empty">Secure acquisition status is unavailable.</div>';if(state)state.textContent=String(error?.message||error)}}
 void load();
})();
""",
    "utf-8",
)


def patch_secure_acquisition_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Expose accepted Bastion/air-gap trust state without exposing quarantine controls."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _SECURE_ACQUISITION_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _SECURE_ACQUISITION_WEB_PATCH,
        response.content_type,
        response.headers,
    )
