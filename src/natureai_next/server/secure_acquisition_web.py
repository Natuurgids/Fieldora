"""Managed-web trust view for FieldoraBastion secure transfer brokering."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_SECURE_ACQUISITION_WEB_PATCH = bytes(
    r"""

/* Fieldora secure acquisition: trusted-side FieldoraBastion transfer-broker visibility. */
(()=>{
 if(window.__fieldoraSecureAcquisitionWired)return;window.__fieldoraSecureAcquisitionWired=true;
 const page=document.getElementById("page-operations");if(!page)return;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const brokerLifecycle=Object.freeze(["requested","acquiring / receiving","quarantined","scanning","verifying","approved","broadcast","claimed","collected"]);
 const section=document.createElement("section");section.id="secure-acquisition";section.className="card section";
 section.innerHTML=`<h2>Secure acquisition</h2><p class="muted">FieldoraBastion is the secure transfer broker for external packages. It accepts collection requests (obtain a package from an approved source) and delivery requests (receive a supplied package), then quarantines, scans, verifies and approves the package before publishing a bounded broadcast for an eligible collector. Fieldora independently verifies signed manifests, clean-scan claims and payload digests before trusted-side acceptance. The browser cannot mark content clean or bypass acceptance policy.</p><div class="row"><div><strong>Broker lifecycle</strong><br><span class="muted">${brokerLifecycle.map(esc).join(" → ")}</span></div></div><p class="muted">A broadcast advertises metadata only; package bytes stay in approved Bastion storage until an authenticated collector claims them. Collection completes with a receipt for the exact approved digest. Connected request/status APIs are not assumed here; air-gap and removable-media transfers preserve the same state and verification semantics.</p><div id="secure-acquisition-summary" class="list"></div><p id="secure-acquisition-status" class="status"></p>`;
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
 async function load(){const list=document.getElementById("secure-acquisition-summary"),state=document.getElementById("secure-acquisition-status");if(!list)return;try{const items=await accepted();list.innerHTML=items.map(item=>`<div class="row"><div><strong>${esc(item.name)}</strong><br><span class="muted">${esc(item.kind)} · trusted-side accepted</span></div><span class="pill">${esc(item.trust)}</span></div>`).join("")||'<div class="empty">No brokered or air-gap packages have been accepted into trusted storage.</div>';if(state)state.textContent="Quarantine, scanner approval, broadcast eligibility and collector claims remain authoritative in FieldoraBastion; this view shows trusted-side acceptance until the connected broker protocol is exposed."}catch(error){list.innerHTML='<div class="empty">Secure acquisition status is unavailable.</div>';if(state)state.textContent=String(error?.message||error)}}
 void load();
})();
""",
    "utf-8",
)


def patch_secure_acquisition_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Expose the Bastion broker contract without exposing quarantine approval controls."""
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
