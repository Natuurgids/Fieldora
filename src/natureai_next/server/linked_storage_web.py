"""Managed-browser UI patch for governed linked scientific storage."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LINKED_STORAGE_WEB_PATCH = bytes(
    r"""

/* Fieldora linked archives: catalogue browse, managed thumbnails and bounded originals. */
(()=>{
 if(window.__fieldoraLinkedStorageWired)return;window.__fieldoraLinkedStorageWired=true;
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const library=byId("page-library"),importCard=byId("import-card");
 if(!library||!importCard)return;

 const style=document.createElement("style");
 style.textContent=`
  .linked-toolbar{display:grid;grid-template-columns:minmax(180px,1fr) minmax(220px,2fr) auto;gap:9px;align-items:end}
  .linked-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
  .linked-card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px;cursor:pointer;min-width:0}
  .linked-card:focus{outline:2px solid var(--green);outline-offset:2px}
  .linked-card img{width:100%;height:130px;object-fit:contain;border-radius:8px;background:#0b1113}
  .linked-card .thumb{height:130px}
  .linked-path{overflow-wrap:anywhere;font-size:12px;color:var(--muted)}
  @media(max-width:700px){.linked-toolbar{grid-template-columns:1fr}}
 `;
 document.head.appendChild(style);

 const panel=document.createElement("section");panel.id="linked-storage-card";panel.className="card section";
 panel.innerHTML=`<h2>Linked archives</h2><p class="muted">Browse organization-controlled storage without copying originals into Fieldora. Only opaque storage identity and relative catalogue paths are shown.</p><div class="linked-toolbar"><label>Linked archive<input id="linked-storage-id" list="linked-storage-sources" autocomplete="off" placeholder="Choose an archive or enter its opaque ID"><datalist id="linked-storage-sources"></datalist></label><label>Folder prefix<input id="linked-storage-prefix" autocomplete="off" placeholder="Optional relative folder, e.g. Amazon/day-01"></label><button id="linked-storage-browse" class="primary">Browse linked archive</button></div><p id="linked-storage-status" class="status"></p><div class="split section"><section><div id="linked-storage-grid" class="linked-gallery"><div class="empty">Choose a linked archive to browse.</div></div></section><aside class="card details"><h3>Linked evidence</h3><div id="linked-storage-detail" class="muted">Select linked evidence to inspect it.</div></aside></div>`;
 importCard.before(panel);

 let linkedItems=[];
 const thumbUrls=new Map();
 const setLinkedStatus=(text,error=false)=>{const node=byId("linked-storage-status");node.textContent=text;node.style.color=error?"var(--danger)":"var(--green)";};
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

 async function loadSources(){
  try{
   const result=await api("/api/v1/linked-storage/sources",{purpose:"research"}),items=result.items||[],list=byId("linked-storage-sources");
   list.innerHTML=items.map(source=>`<option value="${html(source.storage_id)}">${html(source.display_name||source.storage_id)}${source.read_only?" · read only":""}</option>`).join("");
   if(items.length===1&&!byId("linked-storage-id").value)byId("linked-storage-id").value=items[0].storage_id;
   if(items.length)setLinkedStatus(`${items.length} linked archive${items.length===1?"":"s"} available for this organization.`);
  }catch(_error){
   setLinkedStatus("Linked archive discovery is unavailable; enter a known opaque storage ID to continue.");
  }
 }
 function clearThumbUrls(){for(const url of thumbUrls.values())URL.revokeObjectURL(url);thumbUrls.clear()}
 function iconFor(item){const type=String(item.mime_type||"");return type.startsWith("image/")?"▧":type.startsWith("audio/")?"≋":type.startsWith("video/")?"▷":"▤"}
 function renderLinked(){
  clearThumbUrls();
  const grid=byId("linked-storage-grid");
  if(!linkedItems.length){grid.innerHTML='<div class="empty">No governed linked media at this prefix.</div>';return}
  grid.innerHTML=linkedItems.map(item=>`<article class="linked-card" tabindex="0" role="button" data-linked-media="${html(item.media_id)}"><div class="thumb" data-linked-placeholder="${html(item.media_id)}">${iconFor(item)}</div>${String(item.mime_type||"").startsWith("image/")?`<img data-linked-thumbnail="${html(item.media_id)}" alt="Linked evidence thumbnail" hidden>`:""}<p><strong>${html(item.filename||item.media_id)}</strong></p><p class="linked-path">${html(item.relative_path||"")}</p><p class="muted">${(Number(item.size_bytes||0)/1048576).toFixed(2)} MB · ${html(item.thumbnail_state||"missing")}</p></article>`).join("");
  grid.querySelectorAll("[data-linked-media]").forEach(card=>{
   const open=()=>openLinked(card.dataset.linkedMedia);
   card.addEventListener("click",open);
   card.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();open()}});
  });
 }

 async function loadThumb(item){
  if(!String(item.mime_type||"").startsWith("image/"))return;
  try{
   const blob=await api(`/api/v1/linked-storage/thumbnail?media_id=${encodeURIComponent(item.media_id)}`,{purpose:"research"});
   if(!(blob instanceof Blob))return;
   const old=thumbUrls.get(item.media_id);if(old)URL.revokeObjectURL(old);
   const url=URL.createObjectURL(blob);thumbUrls.set(item.media_id,url);
   const img=document.querySelector(`[data-linked-thumbnail="${CSS.escape(item.media_id)}"]`),placeholder=document.querySelector(`[data-linked-placeholder="${CSS.escape(item.media_id)}"]`);
   if(img){img.src=url;img.hidden=false}if(placeholder)placeholder.hidden=true;
  }catch(_error){}
 }
 async function refreshThumbs(){for(const item of linkedItems)await loadThumb(item)}
 async function queueVisiblePreviews(){
  const ids=linkedItems.filter(item=>String(item.mime_type||"").startsWith("image/")&&item.thumbnail_state!=="ready"&&item.thumbnail_state!=="unsupported").map(item=>item.media_id);
  if(!ids.length){await refreshThumbs();return}
  try{await api("/api/v1/linked-storage/previews",{method:"POST",purpose:"research",body:JSON.stringify({media_ids:ids,priority:800,reason:"visible-directory"})})}catch(_error){}
  await refreshThumbs();setTimeout(refreshThumbs,1500);setTimeout(refreshThumbs,4000);
 }

 async function browseLinked(){
  const storageId=byId("linked-storage-id").value.trim(),prefix=byId("linked-storage-prefix").value.trim();
  if(!storageId)return setLinkedStatus("Choose a linked archive or enter its opaque storage ID.",true);
  setLinkedStatus("Loading linked catalogue…");
  try{
   const result=await api(`/api/v1/linked-storage/browse?storage_id=${encodeURIComponent(storageId)}&prefix=${encodeURIComponent(prefix)}&limit=500`,{purpose:"research"});
   linkedItems=result.items||[];renderLinked();setLinkedStatus(`${linkedItems.length} governed linked item${linkedItems.length===1?"":"s"} · originals remain on organization storage.`);await queueVisiblePreviews();
  }catch(error){linkedItems=[];renderLinked();setLinkedStatus(error.message,true)}
 }

 function openLinked(mediaId){
  const item=linkedItems.find(value=>value.media_id===mediaId);if(!item)return;
  const detail=byId("linked-storage-detail"),metadata=JSON.stringify(item.metadata||{},null,2);
  detail.innerHTML=`<h3>${html(item.filename||item.media_id)}</h3><p>${html(item.mime_type||"application/octet-stream")} · ${(Number(item.size_bytes||0)/1048576).toFixed(2)} MB</p><p>Relative path<br><code>${html(item.relative_path||"")}</code></p><p>Media ID<br><code>${html(item.media_id)}</code></p><p>SHA-256<br><code>${html(item.sha256||"not established")}</code></p><pre>${html(metadata)}</pre><div class="actions"><button id="linked-request-preview">Request preview</button><button id="linked-download-original" class="primary">Retrieve governed original</button></div><p id="linked-detail-status" class="status"></p>`;
  byId("linked-request-preview").onclick=async()=>{try{await api("/api/v1/linked-storage/previews",{method:"POST",purpose:"research",body:JSON.stringify({media_ids:[item.media_id],priority:1000,reason:"opened-detail"})});byId("linked-detail-status").textContent="Preview requested.";setTimeout(()=>loadThumb(item),1200)}catch(error){byId("linked-detail-status").textContent=error.message}};
  byId("linked-download-original").onclick=()=>downloadLinkedOriginal(item);
 }

 async function awaitRange(requestId){
  for(let attempt=0;attempt<120;attempt++){
   const response=await api(`/api/v1/linked-storage/ranges?request_id=${encodeURIComponent(requestId)}`,{purpose:"research"});
   if(response instanceof Blob)return response;
   if(response&&response.state!=="pending"&&response.state!=="leased")throw new Error(`Original range ${response.state||"unavailable"}`);
   await sleep(500);
  }
  throw new Error("Timed out waiting for storage service range.");
 }
 async function downloadLinkedOriginal(item){
  const detailStatus=byId("linked-detail-status"),total=Number(item.size_bytes||0),chunk=4*1024*1024,maxBrowser=512*1024*1024;
  if(!Number.isSafeInteger(total)||total<1)return detailStatus.textContent="Original size is unavailable.";
  if(total>maxBrowser)return detailStatus.textContent="This original exceeds the 512 MiB browser retrieval limit. Use a governed export or desktop workflow for very large evidence.";
  const parts=[];
  try{
   for(let start=0;start<total;start+=chunk){
    const end=Math.min(total-1,start+chunk-1);detailStatus.textContent=`Requesting original · ${Math.floor(start/total*100)}%`;
    const queued=await api("/api/v1/linked-storage/ranges",{method:"POST",purpose:"research",body:JSON.stringify({media_id:item.media_id,start_byte:start,end_byte:end})});
    parts.push(await awaitRange(queued.request_id));
   }
   const original=new Blob(parts,{type:item.mime_type||"application/octet-stream"}),url=URL.createObjectURL(original),a=document.createElement("a");
   a.href=url;a.download=item.filename||`fieldora-linked-${item.media_id}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);detailStatus.textContent="Governed original retrieved.";
  }catch(error){detailStatus.textContent=error.message}
 }

 byId("linked-storage-browse").onclick=browseLinked;
 byId("linked-storage-prefix").addEventListener("keydown",event=>{if(event.key==="Enter")browseLinked()});
 window.addEventListener("beforeunload",clearThumbUrls,{once:true});
 loadSources();
})();
""",
    "utf-8",
)


def patch_linked_storage_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append linked-storage browser behavior only to the managed app bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _LINKED_STORAGE_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LINKED_STORAGE_WEB_PATCH,
        response.content_type,
        response.headers,
    )
