"""Operator browser projection for linked archive service health."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LINKED_STORAGE_OPERATOR_WEB_PATCH = bytes(
    r"""

/* Fieldora Operator: linked archive ownership and storage-service freshness. */
(()=>{
 if(window.__fieldoraLinkedStorageOperatorWired)return;
 window.__fieldoraLinkedStorageOperatorWired=true;
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

 async function loadLinkedArchives(){
  const target=byId("operator-linked-archives");if(!target)return;
  try{
   const overview=await api("/api/v1/operator/overview",{purpose:"administration"}),items=overview.linked_archives||[];
   target.innerHTML=items.length?items.map(item=>{
    const age=item.heartbeat_age_seconds==null?"no heartbeat":`${item.heartbeat_age_seconds}s heartbeat age`;
    const health=item.stale?"Needs attention":"Healthy";
    return `<div class="row"><strong>${html(item.display_name||item.storage_id)}</strong><span>${html(item.storage_id)} · ${html(item.service_name||item.service_id)}</span><span class="pill">${html(item.service_state)} · ${html(health)}</span><span>${html(item.node_name||"unregistered node")} · ${html(age)}${item.read_only?" · read only":""}</span></div>`;
   }).join(""):'<div class="empty">No linked archives registered for this organization.</div>';
  }catch(error){target.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 }

 function enhanceOperator(){
  const page=byId("page-operator");if(!page)return false;
  if(!byId("operator-linked-archives")){
   const section=document.createElement("section");section.className="card section";
   section.innerHTML='<h2>Linked archives</h2><p class="muted">Archive ownership, enrolled storage service and heartbeat freshness. Filesystem mount details remain storage-node private.</p><div id="operator-linked-archives" class="list"></div>';
   const storage=byId("operator-storage")?.closest("section");
   if(storage)storage.after(section);else page.appendChild(section);
  }
  const nav=document.querySelector('.nav[data-page="operator"]');
  if(nav&&!nav.dataset.linkedArchivesWired){nav.dataset.linkedArchivesWired="true";nav.addEventListener("click",()=>setTimeout(loadLinkedArchives,0))}
  const refresh=byId("operator-refresh");
  if(refresh&&!refresh.dataset.linkedArchivesWired){refresh.dataset.linkedArchivesWired="true";refresh.addEventListener("click",()=>setTimeout(loadLinkedArchives,0))}
  if(!page.hidden)loadLinkedArchives();
  return true;
 }

 if(!enhanceOperator()){
  const observer=new MutationObserver(()=>{if(enhanceOperator())observer.disconnect()});
  observer.observe(document.body,{childList:true,subtree:true});
 }
})();
""",
    "utf-8",
)


def patch_linked_storage_operator_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append linked archive Operator behavior only to the managed app bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _LINKED_STORAGE_OPERATOR_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LINKED_STORAGE_OPERATOR_WEB_PATCH,
        response.content_type,
        response.headers,
    )
