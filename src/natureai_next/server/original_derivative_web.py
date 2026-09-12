"""Managed-browser rendering for governed original/derivative lineage."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ORIGINAL_DERIVATIVE_PATCH = bytes(
    r"""

/* WEB-039: derivatives are lineage-linked artifacts, never replacements for originals. */
(()=>{
 if(window.__fieldoraOriginalDerivativeWired)return;
 window.__fieldoraOriginalDerivativeWired=true;
 const grid=document.getElementById("media-grid"),detail=document.getElementById("media-detail");
 if(!grid||!detail)return;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 grid.addEventListener("click",async event=>{
  const card=event.target.closest("[data-media]");if(!card)return;
  const selected=(typeof media!=="undefined"?media:[]).find(item=>item.media_id===card.dataset.media);if(!selected)return;
  detail.querySelector("#media-original-derivative-detail")?.remove();
  const section=document.createElement("section");section.id="media-original-derivative-detail";section.className="section";
  section.innerHTML='<p class="muted">Loading original/derivative lineage…</p>';detail.appendChild(section);
  try{
   const payload=await api(`/api/v1/media/${encodeURIComponent(selected.media_id)}/derivatives`,{purpose:"research"});
   const source=payload.source||{},items=payload.items||[];
   const rows=items.length?items.map(item=>`<div class="row"><strong>${esc(item.kind)}</strong><span>${esc(item.mime_type)} · ${Number(item.size_bytes||0).toLocaleString()} bytes</span><span><code>${esc(item.sha256)}</code></span><span class="muted">derived from <code>${esc(item.source_sha256)}</code></span></div>`).join(""):'<p class="muted">No registered derivatives.</p>';
   section.innerHTML=`<h3>Original &amp; derivatives</h3><p><strong>Governed original</strong><br><code>${esc(source.media_id)}</code> · <code>${esc(source.sha256)}</code></p><p class="muted">The governed original is authoritative. Thumbnails, previews, transcodes, and analysis outputs are separate lineage-linked artifacts and never replace or silently mutate it.</p><div id="media-derivative-list">${rows}</div>`;
  }catch(error){section.innerHTML=`<p class="status" style="color:var(--danger)">${esc(error?.message||"Derivative lineage unavailable")}</p>`}
 });
})();
""",
    "utf-8",
)


def patch_original_derivative_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _ORIGINAL_DERIVATIVE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _ORIGINAL_DERIVATIVE_PATCH,
        response.content_type,
        response.headers,
    )
