"""Operator browser projection for linked archive service health and lifecycle."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LINKED_STORAGE_OPERATOR_WEB_PATCH = bytes(
    r"""

/* Fieldora Operator: durable jobs plus linked archive ownership and lifecycle. */
(()=>{
 if(window.__fieldoraLinkedStorageOperatorWired)return;
 window.__fieldoraLinkedStorageOperatorWired=true;
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

 function renderJobs(jobs){
  const target=byId("operator-jobs");if(!target)return;
  const counts=jobs?.by_status||{},recent=jobs?.recent||[];
  const summary=Object.entries(counts).map(([state,count])=>`${state}: ${count}`).join(" · ")||"No queued work";
  target.outerHTML=`<div id="operator-jobs"><p class="muted" id="operator-job-summary">${html(summary)}</p><div id="operator-job-list" class="list">${recent.length?recent.map(job=>{
   const when=job.updated_at_utc?new Date(job.updated_at_utc).toLocaleString():"unknown time";
   const scope=job.project_id?`project ${job.project_id}`:"organization scope";
   const worker=job.lease_owner?` · worker ${job.lease_owner}`:"";
   return `<div class="row" data-operator-job="${html(job.job_id)}"><strong>${html(job.job_type)}</strong><span>${html(job.job_id)} · ${html(scope)}</span><span class="pill">${html(job.status)} · attempt ${html(job.attempts)}</span><span>${html(when+worker)}</span></div>`;
  }).join(""):'<div class="empty">No durable jobs recorded for this organization.</div>'}</div></div>`;
 }

 async function setArchiveEnabled(storageId,enabled){
  const status=byId("operator-linked-archives-status"),operation=enabled?"enable":"disable";
  if(status)status.textContent=`${enabled?"Enabling":"Disabling"} linked archive…`;
  try{
   await api(`/api/v1/operator/linked-archives/${encodeURIComponent(storageId)}/${operation}`,{method:"POST",purpose:"administration",body:"{}"});
   if(status)status.textContent=`Linked archive ${enabled?"enabled":"disabled"}.`;
   await loadOperatorExtensions();
  }catch(error){if(status)status.textContent=error.message}
 }

 function renderArchiveEvents(events){
  const target=byId("operator-linked-archive-events");if(!target)return;
  target.innerHTML=events.length?events.map(event=>{
   const when=event.occurred_at?new Date(event.occurred_at).toLocaleString():"unknown time";
   return `<div class="row" data-linked-archive-event="${html(event.event_type)}"><strong>${html(event.event_type)}</strong><span>${html(event.storage_id)} · ${html(event.actor_id)}</span><span>${html(when)}</span></div>`;
  }).join(""):'<div class="empty">No linked archive lifecycle events recorded.</div>';
 }

 async function loadOperatorExtensions(){
  const target=byId("operator-linked-archives");if(!target)return;
  try{
   const overview=await api("/api/v1/operator/overview",{purpose:"administration"}),items=overview.linked_archives||[];
   renderJobs(overview.jobs||{});
   target.innerHTML=items.length?items.map(item=>{
    const enabled=item.enabled!==false,age=item.heartbeat_age_seconds==null?"no heartbeat":`${item.heartbeat_age_seconds}s heartbeat age`;
    const health=!enabled?"Disabled":item.stale?"Needs attention":"Healthy",operation=enabled?"disable":"enable",label=enabled?"Disable archive":"Enable archive";
    return `<div class="row" data-linked-archive="${html(item.storage_id)}"><strong>${html(item.display_name||item.storage_id)}</strong><span>${html(item.storage_id)} · ${html(item.service_name||item.service_id)}</span><span class="pill">${html(item.service_state)} · ${html(health)}</span><span>${html(item.node_name||"unregistered node")} · ${html(age)}${item.read_only?" · read only":""}</span><div class="actions"><button data-linked-archive-action="${operation}" data-linked-storage-id="${html(item.storage_id)}">${label}</button></div></div>`;
   }).join(""):'<div class="empty">No linked archives registered for this organization.</div>';
   renderArchiveEvents(overview.linked_archive_events||[]);
   target.querySelectorAll("[data-linked-archive-action]").forEach(button=>button.addEventListener("click",()=>setArchiveEnabled(button.dataset.linkedStorageId,button.dataset.linkedArchiveAction==="enable")));
  }catch(error){target.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 }

 function enhanceOperator(){
  const page=byId("page-operator");if(!page)return false;
  if(!byId("operator-linked-archives")){
   const section=document.createElement("section");section.className="card section";
   section.innerHTML='<h2>Linked archives</h2><p class="muted">Archive ownership, enrolled storage service and heartbeat freshness. Disablement revokes Library access without exposing or changing storage-node paths.</p><p id="operator-linked-archives-status" class="status"></p><div id="operator-linked-archives" class="list"></div><h3>Recent lifecycle activity</h3><p class="muted">Newest registration and Operator lifecycle events for this organization.</p><div id="operator-linked-archive-events" class="list"></div>';
   const storage=byId("operator-storage")?.closest("section");
   if(storage)storage.after(section);else page.appendChild(section);
  }
  const nav=document.querySelector('.nav[data-page="operator"]');
  if(nav&&!nav.dataset.linkedArchivesWired){nav.dataset.linkedArchivesWired="true";nav.addEventListener("click",()=>setTimeout(loadOperatorExtensions,0))}
  const refresh=byId("operator-refresh");
  if(refresh&&!refresh.dataset.linkedArchivesWired){refresh.dataset.linkedArchivesWired="true";refresh.addEventListener("click",()=>setTimeout(loadOperatorExtensions,0))}
  if(!page.hidden)loadOperatorExtensions();
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
