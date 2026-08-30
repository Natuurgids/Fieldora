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
 let operatorOrganizationId="";

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

 async function activateStorageService(serviceId){
  const status=byId("operator-linked-service-setup-status");
  if(status)status.textContent="Activating enrolled storage service…";
  try{
   await api(`/api/v1/operator/services/${encodeURIComponent(serviceId)}/activate`,{method:"POST",purpose:"administration",body:"{}"});
   if(status)status.textContent="Storage service active. Configure the storage node with the handoff values below; the node registers its read-only archive over mTLS.";
   await loadOperatorExtensions();
  }catch(error){if(status)status.textContent=error.message}
 }

 function renderStorageHandoff(service){
  const target=byId("operator-linked-service-handoff");if(!target)return;
  target.hidden=false;
  target.innerHTML=`<h3>Storage-node handoff</h3><p class="muted">Use these non-secret identifiers on the storage node. Root paths, root aliases, private keys, CA material and source credentials are configured only on that node and are never sent through this browser form.</p><div class="list"><div class="row"><strong>Service ID</strong><code>${html(service.service_id)}</code></div><div class="row"><strong>Organization ID</strong><code>${html(operatorOrganizationId)}</code></div><div class="row"><strong>Service type</strong><code>linked-storage</code></div><div class="row"><strong>State</strong><span class="pill">${html(service.state)}</span></div></div><div class="actions section"><button id="operator-linked-service-activate" class="primary" type="button">Activate storage service</button></div>`;
  byId("operator-linked-service-activate")?.addEventListener("click",()=>activateStorageService(service.service_id));
 }

 async function prepareStorageServiceId(){
  const status=byId("operator-linked-service-setup-status");
  if(status)status.textContent="Preparing an opaque storage-service identity…";
  try{
   const prepared=await api("/api/v1/operator/linked-storage-services/prepare-id",{method:"POST",purpose:"administration",body:"{}"});
   const serviceId=String(prepared.service_id||"");
   if(!serviceId)throw new Error("Server did not prepare a storage-service identity.");
   const field=byId("operator-linked-service-id");if(field)field.value=serviceId;
   const command=byId("operator-linked-service-trust-command");
   if(command){command.hidden=false;command.innerHTML=`<p class="muted">Create the mTLS certificate on the trusted Fieldora host before enrollment. The certificate must contain this exact service ID.</p><code>./New-Fieldora-Storage-ServiceTrust.ps1 -ServiceId ${html(serviceId)} -Organization ${html(operatorOrganizationId||"&lt;organization&gt;")}</code><p class="muted">Paste only the returned certificate serial and expiry below. Do not paste private keys or CA material into the browser.</p>`;}
   if(status)status.textContent="Service identity prepared. Create its mTLS certificate, then enter the certificate serial and expiry to enroll it.";
  }catch(error){if(status)status.textContent=error.message}
 }

 async function enrollStorageService(){
  const status=byId("operator-linked-service-setup-status");
  const serviceId=byId("operator-linked-service-id")?.value.trim()||"";
  const name=byId("operator-linked-service-name")?.value.trim()||"";
  const nodeName=byId("operator-linked-service-node")?.value.trim()||"";
  const serial=byId("operator-linked-service-certificate-serial")?.value.trim()||"";
  const expires=byId("operator-linked-service-certificate-expiry")?.value||"";
  const expiryEpoch=expires?Math.floor(new Date(`${expires}T23:59:59Z`).getTime()/1000):0;
  if(!serviceId||!name||!nodeName||!serial||!expiryEpoch){if(status)status.textContent="Prepare a service ID first; service name, node name, certificate serial and certificate expiry are also required.";return}
  if(status)status.textContent="Enrolling durable linked-storage service identity…";
  try{
   const created=await api("/api/v1/operator/linked-storage-services",{method:"POST",purpose:"administration",body:JSON.stringify({service_id:serviceId,name,node_name:nodeName,software_version:"",configuration_sha256:"",certificate_serial:serial,certificate_not_after_epoch:expiryEpoch})});
   const service=created.service;
   if(!service?.service_id||service.service_id!==serviceId)throw new Error("Server returned a different service identity.");
   if(status)status.textContent=`Storage service enrolled as ${service.service_id}. It is not active until explicitly activated.`;
   renderStorageHandoff(service);
   await loadOperatorExtensions();
  }catch(error){if(status)status.textContent=error.message}
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
   operatorOrganizationId=String(overview.organization_id||"");
   renderJobs(overview.jobs||{});
   target.innerHTML=items.length?items.map(item=>{
    const enabled=item.enabled!==false,age=item.heartbeat_age_seconds==null?"no heartbeat":`${item.heartbeat_age_seconds}s heartbeat age`;
    const health=!enabled?"Disabled":item.stale?"Needs attention":"Healthy",operation=enabled?"disable":"enable",label=enabled?"Disable archive":"Enable archive";
    return `<div class="row" data-linked-archive="${html(item.storage_id)}"><strong>${html(item.display_name||item.storage_id)}</strong><span>${html(item.storage_id)} · ${html(item.service_name||item.service_id)}</span><span class="pill">${html(item.service_state)} · ${html(health)}</span><span>${html(item.node_name||"unregistered node")} · ${html(age)}${item.read_only?" · read only":""}</span><div class="actions"><button data-linked-archive-action="${operation}" data-linked-storage-id="${html(item.storage_id)}">${label}</button></div></div>`;
   }).join(""):'<div class="empty">No linked archives registered for this organization. Prepare, enroll and activate a linked-storage service below, then complete archive registration from that storage node.</div>';
   renderArchiveEvents(overview.linked_archive_events||[]);
   target.querySelectorAll("[data-linked-archive-action]").forEach(button=>button.addEventListener("click",()=>setArchiveEnabled(button.dataset.linkedStorageId,button.dataset.linkedArchiveAction==="enable")));
  }catch(error){target.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 }

 function enhanceOperator(){
  const page=byId("page-operator");if(!page)return false;
  if(!byId("operator-linked-archives")){
   const section=document.createElement("section");section.className="card section";
   section.innerHTML='<h2>Linked archives</h2><p class="muted">Archive ownership, enrolled storage service and heartbeat freshness. Disablement revokes Library access without exposing or changing storage-node paths.</p><p id="operator-linked-archives-status" class="status"></p><div id="operator-linked-archives" class="list"></div><h3>Connect a storage service</h3><p class="muted">Prepare the durable service identity first, create its mTLS certificate on the trusted Fieldora host, then enroll and activate it. Filesystem roots, aliases, private keys, CA certificates and storage credentials stay on the storage node.</p><div class="form-grid"><label>Service ID<input id="operator-linked-service-id" readonly autocomplete="off" placeholder="Prepare an identity first"></label><label>Service name<input id="operator-linked-service-name" autocomplete="off" placeholder="Herbarium archive service"></label><label>Node name<input id="operator-linked-service-node" autocomplete="off" placeholder="archive-node-01"></label><label>Certificate serial<input id="operator-linked-service-certificate-serial" autocomplete="off"></label><label>Certificate expiry<input id="operator-linked-service-certificate-expiry" type="date"></label></div><div class="actions section"><button id="operator-linked-service-prepare" type="button">Prepare service ID</button><button id="operator-linked-service-enroll" class="primary" type="button">Enroll linked-storage service</button></div><p id="operator-linked-service-setup-status" class="status"></p><div id="operator-linked-service-trust-command" class="section" hidden></div><div id="operator-linked-service-handoff" class="section" hidden></div><h3>Recent lifecycle activity</h3><p class="muted">Newest registration and Operator lifecycle events for this organization.</p><div id="operator-linked-archive-events" class="list"></div>';
   const storage=byId("operator-storage")?.closest("section");
   if(storage)storage.after(section);else page.appendChild(section);
   byId("operator-linked-service-prepare")?.addEventListener("click",prepareStorageServiceId);
   byId("operator-linked-service-enroll")?.addEventListener("click",enrollStorageService);
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
