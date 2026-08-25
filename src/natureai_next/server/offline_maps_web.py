"""Managed-web discovery for verified offline map packages."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_OFFLINE_MAPS_WEB_PATCH = br"""

/* Fieldora offline maps: verified package metadata only, never host paths. */
(()=>{
 if(window.__fieldoraOfflineMapsWired)return;window.__fieldoraOfflineMapsWired=true;
 const page=document.getElementById("page-operations");if(!page)return;
 const escMap=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const section=document.createElement("section");section.id="offline-map-packages";section.className="card section";
 section.innerHTML=`<h2>Installed offline map packages</h2><p class="muted">Verified Bastion/air-gap map packages available to Facilities. Only bounded trust metadata is shown; server and Bastion filesystem paths remain private.</p><p class="muted"><strong>Local / USB import:</strong> an organization administrator can install approved map data from removable media with <code>Install-Fieldora-Offline-Media.ps1</code>. The trusted signing public key, signed manifest, clean-scan attestation and payload hashes remain mandatory.</p><div id="offline-map-list" class="list"></div><p id="offline-map-status" class="status"></p>`;
 const planning=document.getElementById("facility-planning-web");if(planning)planning.insertAdjacentElement("beforebegin",section);else page.appendChild(section);
 async function loadOfflineMaps(){const list=document.getElementById("offline-map-list"),state=document.getElementById("offline-map-status");if(!list)return;try{const result=await api("/api/v1/maps/installed",{purpose:"administration"});const items=result.items||[];list.innerHTML=items.map(item=>{const size=(Number(item.artifact_total_bytes||0)/1073741824).toFixed(2),trust=item.manifest_signature==="ed25519"?(item.malware_scan?.result==="clean"?"Signed + clean scanned":"Signed manifest"):"Unsigned local bundle";return `<div class="row"><div><strong>${escMap(item.name||item.map_id)}</strong><br><span class="muted">${escMap(item.version)} · ${escMap((item.formats||[]).join(", "))}</span></div><span>${size} GiB</span><span>${escMap(item.license_id||"unspecified")}</span><span class="pill">${escMap(trust)}</span></div>`}).join("")||'<div class="empty">No verified offline map packages are installed.</div>';if(state)state.textContent=""}catch(error){const message=String(error?.message||error);list.innerHTML=message.includes("offline_map_store_unavailable")?'<div class="empty">Offline map storage is not configured on this server.</div>':'<div class="empty">Installed map discovery is unavailable.</div>';if(state)state.textContent=message.includes("offline_map_store_unavailable")?"":message}}
 const baseLoadOperations=loadOperations;loadOperations=async function(){await baseLoadOperations();await loadOfflineMaps()};
 document.getElementById("operations-refresh")?.addEventListener("click",loadOfflineMaps);
 document.querySelectorAll('.nav[data-page="operations"]').forEach(button=>button.addEventListener("click",loadOfflineMaps));
})();
"""


def patch_offline_maps_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _OFFLINE_MAPS_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(response.status, response.body + _OFFLINE_MAPS_WEB_PATCH, response.content_type, response.headers)
