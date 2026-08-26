"""Governed Library evidence-detail rendering for the managed browser."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_MEDIA_DETAIL_PATCH = bytes(
    r"""

/* Fieldora governed evidence detail: identity plus authorized provenance links. */
(()=>{
 if(window.__fieldoraGovernedMediaDetailWired)return;
 window.__fieldoraGovernedMediaDetailWired=true;
 const grid=document.getElementById("media-grid"),detail=document.getElementById("media-detail");
 if(!grid||!detail)return;
 const legacy=grid.onclick;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const labels={project:"Project",collection:"Collection / dataset",dossier:"Dossier",submission:"Submission",review_case:"Review case"};
 grid.onclick=async e=>{
  legacy?.call(grid,e);
  const card=e.target.closest("[data-media]");if(!card)return;
  const selected=(typeof media!=="undefined"?media:[]).find(item=>item.media_id===card.dataset.media);if(!selected)return;
  detail.querySelector("#media-governed-detail")?.remove();
  const section=document.createElement("section");section.id="media-governed-detail";section.className="section";
  section.innerHTML='<p class="muted">Loading governed identity and provenance…</p>';detail.appendChild(section);
  try{
   const context=selected.project_id?`?project_id=${encodeURIComponent(selected.project_id)}`:"";
   const payload=await api(`/api/v1/media/${encodeURIComponent(selected.media_id)}/detail${context}`,{purpose:"research"});
   const item=payload.item||{},links=payload.associations||[];
   const relationshipRows=links.length?links.map(link=>`<div class="row"><strong>${esc(labels[link.association_type]||link.association_type)}</strong><span><code>${esc(link.target_id)}</code></span><span>${esc(link.purpose||"research")}</span><span class="muted">linked by ${esc(link.linked_by||"—")} · ${esc(link.linked_at_epoch||"—")}</span></div>`).join(""):'<p class="muted">No additional authorized relationships are disclosed.</p>';
   section.innerHTML=`<h3>Governed identity</h3><p><strong>Media ID</strong><br><code>${esc(item.media_id)}</code></p><p><strong>Content type</strong><br>${esc(item.mime_type||"application/octet-stream")}</p><p><strong>File size</strong><br>${Number(item.size_bytes||0).toLocaleString()} bytes</p><p><strong>SHA-256</strong><br><code>${esc(item.sha256)}</code></p><h3 class="section">Relationships &amp; provenance</h3><div id="media-association-detail">${relationshipRows}</div>`;
  }catch(error){
   section.innerHTML=`<p class="status" style="color:var(--danger)">${esc(error?.message||"Governed detail unavailable")}</p>`;
  }
 };
})();
""",
    "utf-8",
)


def patch_media_detail_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the evidence-detail behavior once, after the standard browser patches."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _MEDIA_DETAIL_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _MEDIA_DETAIL_PATCH,
        response.content_type,
        response.headers,
    )
