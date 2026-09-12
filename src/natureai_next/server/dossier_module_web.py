"""Module-owned Dossier workspace for managed web.

This adapter establishes an independently mountable Dossier owner before the
legacy `/dossiers` wiring is retired. It consumes Project context through the
public `projects.context.select` contract and deliberately does not acquire the
Project list contract or ambient `projects` state.

The Dossier data service below is the stable presentation/transport boundary.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_DOSSIER_DATA_SERVICE_PATCH = bytes(
    r"""

/* WEB-DOSSIER-DATA-SERVICE: Dossier-owned transport boundary. */
(()=>{
 if(window.__fieldoraDossierDataServiceWired)return;window.__fieldoraDossierDataServiceWired=true;
 const moduleId="dossiers.workspace",contractName="dossiers.data.service";
 const freezeItems=items=>Object.freeze((Array.isArray(items)?items:[]).map(item=>Object.freeze({...item})));
 async function load(){const [dossiers,reviews]=await Promise.all([api("/api/v1/dossiers"),api("/api/v1/dossier-reviews")]);return Object.freeze({dossiers:freezeItems(dossiers?.items),reviews:freezeItems(reviews?.items)})}
 async function createDossier(record){return api("/api/v1/dossiers",{method:"POST",body:JSON.stringify({...record})})}
 async function createReview(record){return api("/api/v1/dossier-reviews",{method:"POST",body:JSON.stringify({...record})})}
 async function libraryItems(){const result=await api("/api/v1/media?limit=200",{purpose:"research"});return freezeItems(result?.items)}
 async function evidence(dossierId){const id=String(dossierId||"").trim();if(!id)return Object.freeze([]);const result=await api(`/api/v1/dossiers/${encodeURIComponent(id)}/media-links`,{purpose:"research"});return freezeItems(result?.items)}
 async function linkEvidence(dossierId,mediaId){const did=String(dossierId||"").trim(),mid=String(mediaId||"").trim();if(!did||!mid)throw new Error("Dossier and evidence identifiers are required.");const result=await api(`/api/v1/dossiers/${encodeURIComponent(did)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mid})});return result?.item?Object.freeze({...result.item}):null}
 async function unlinkEvidence(dossierId,mediaId){const did=String(dossierId||"").trim(),mid=String(mediaId||"").trim();if(!did||!mid)throw new Error("Dossier and evidence identifiers are required.");return api(`/api/v1/dossiers/${encodeURIComponent(did)}/media-links/${encodeURIComponent(mid)}`,{method:"DELETE",purpose:"research"})}
 const implementation=Object.freeze({load,createDossier,createReview,libraryItems,evidence,linkEvidence,unlinkEvidence});
 function register(){const contracts=window.FieldoraModuleContracts;if(!contracts)return false;const current=contracts.resolve(contractName);if(current)return current===implementation;contracts.register(contractName,moduleId,implementation);return true}
 register();document.addEventListener('fieldora:contracts-ready',register,{once:true});
})();
""",
    "utf-8",
)

_DOSSIER_MODULE_PATCH = bytes(
    r"""

/* WEB-DOSSIER-MODULE: bounded dossier workspace owner. */
(()=>{
 if(window.__fieldoraDossierModuleWired)return;window.__fieldoraDossierModuleWired=true;
 const moduleId="dossiers.workspace",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",dossiers:[],reviews:[],identityId:"",selectedDossierId:""};
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const nameOf=record=>record?.name||record?.title||record?.id||"Record";
 function currentUser(){return window.FieldoraModuleContracts?.resolve?.("auth.current-user")?.current?.()||null}
 function context(){return window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null}
 function notifications(){return window.FieldoraModuleContracts?.resolve?.("notifications.publish")||null}
 function dataService(){return window.FieldoraModuleContracts?.resolve?.("dossiers.data.service")||null}
 function currentProject(){return String(context()?.current?.()||"")}
 function report(error,fallback){const text=error?.message||fallback,node=q("dossier-status");if(node){node.textContent=text;node.style.color="var(--danger)"}notifications()?.publish?.(String(text),{level:"error",source_module:moduleId})}
 function clearStatus(){const node=q("dossier-status");if(node){node.textContent="";node.style.color=""}}
 function syncProjectContext(){state.projectId=currentProject();const selector=q("dossier-project");if(selector&&state.projectId&&selector.value!==state.projectId)selector.value=state.projectId;return state.projectId}
 function ensureEvidenceSurface(){const page=q("page-dossiers");if(!page||q("dossier-evidence-panel"))return;const panel=document.createElement("section");panel.id="dossier-evidence-panel";panel.className="card section";panel.hidden=true;panel.innerHTML='<h2>Dossier evidence</h2><p class="muted">Reference existing governed Library evidence by its stable media identity. Linking does not copy or replace the Library item.</p><label>Existing Library evidence<select id="dossier-evidence-select"><option value="">Choose evidence…</option></select></label><div class="actions section"><button id="dossier-evidence-link" class="primary" type="button">Link evidence</button></div><div id="dossier-evidence-list"></div><p id="dossier-evidence-status" class="status"></p>';q("dossier-workspace-detail")?.after(panel)}
 function render(){const host=q("dossier-workspace-list");if(!host)return;const children=new Map();for(const dossier of state.dossiers){const parent=dossier.parent_dossier_id||"";if(!children.has(parent))children.set(parent,[]);children.get(parent).push(dossier)}const rows=[];const walk=(parent,depth)=>{for(const dossier of children.get(parent)||[]){rows.push(`<button type="button" class="row" data-dossier-workspace="${esc(dossier.id)}"><strong>${" ".repeat(depth)}${depth?"↳ ":""}${esc(nameOf(dossier))}</strong><span>${esc(dossier.dossier_type||"dossier")}</span><span>${esc(dossier.review_status||dossier.status||"draft")}</span></button>`);walk(dossier.id,depth+1)}};walk("",0);host.innerHTML=rows.join("")||'<p class="empty">No dossiers.</p>'}
 async function refreshEvidence(){const panel=q("dossier-evidence-panel"),host=q("dossier-evidence-list"),select=q("dossier-evidence-select");if(!panel||!host||!select)return;const dossierId=state.selectedDossierId;if(!dossierId){panel.hidden=true;host.innerHTML="";return}panel.hidden=false;try{const service=dataService();if(!service?.evidence||!service?.libraryItems)throw new Error("Dossier data service is unavailable.");const [linked,library]=await Promise.all([service.evidence(dossierId),service.libraryItems()]);select.innerHTML='<option value="">Choose evidence…</option>';library.filter(item=>!linked.some(link=>link.media_id===item.media_id)).forEach(item=>{const option=document.createElement("option");option.value=item.media_id;option.textContent=`${item.mime_type||"evidence"} · ${String(item.filename||item.name||item.media_id).slice(0,48)}`;select.appendChild(option)});host.innerHTML=linked.length?linked.map(item=>`<div class="row" data-dossier-evidence="${esc(item.media_id)}"><strong>${esc(item.mime_type||"evidence")}</strong><span>${esc(item.media_id)}</span><span>${esc(item.sha256||"")}</span><button type="button" data-dossier-evidence-unlink="${esc(item.media_id)}">Unlink</button></div>`).join(""):'<p class="empty">No Library evidence linked.</p>';q("dossier-evidence-status").textContent=""}catch(error){host.innerHTML="";q("dossier-evidence-status").textContent=error?.message||"Dossier evidence could not be loaded."}}
 async function renderDetail(id){state.selectedDossierId=id;const dossier=state.dossiers.find(item=>item.id===id),host=q("dossier-workspace-detail");if(host){const reviews=state.reviews.filter(item=>item.dossier_id===dossier?.id);host.innerHTML=`<h3>${esc(nameOf(dossier||{}))}</h3><pre>${esc(JSON.stringify(dossier||{},null,2))}</pre><h4>Review history</h4><pre>${esc(JSON.stringify(reviews,null,2))}</pre>`}await refreshEvidence()}
 async function refresh(){try{const service=dataService();if(!service?.load)throw new Error("Dossier data service is unavailable.");const snapshot=await service.load();state.dossiers=[...(snapshot?.dossiers||[])];state.reviews=[...(snapshot?.reviews||[])];render();clearStatus();if(state.selectedDossierId&&!state.dossiers.some(item=>item.id===state.selectedDossierId)){state.selectedDossierId="";const panel=q("dossier-evidence-panel");if(panel)panel.hidden=true}return state.dossiers.slice()}catch(error){state.dossiers=[];state.reviews=[];render();report(error,"Dossiers could not be loaded.");return []}}
 async function ensureIdentity(){if(state.identityId)return state.identityId;const identity=currentUser();state.identityId=String(identity?.identity_id||"");if(!state.identityId)report(null,"Identity could not be loaded.");return state.identityId}
 async function save(){const projectId=syncProjectContext();if(!projectId){report(null,"Select a Project before creating a dossier.");return false}const ownerId=q("dossier-owner")?.value||await ensureIdentity();const record={id:crypto.randomUUID(),project_id:projectId,name:q("dossier-name")?.value||"",description:q("dossier-description")?.value||"",dossier_type:q("dossier-type")?.value||"",parent_dossier_id:q("dossier-parent")?.value||"",owner_id:ownerId,reviewer_id:q("dossier-reviewer")?.value||"",review_status:q("dossier-review-status")?.value||"",status:"active"};try{const service=dataService();if(!service?.createDossier||!service?.createReview)throw new Error("Dossier data service is unavailable.");await service.createDossier(record);const remark=q("dossier-remark")?.value||"";if(remark)await service.createReview({id:crypto.randomUUID(),project_id:projectId,dossier_id:record.id,reviewer_id:record.reviewer_id,remark,status:record.review_status,recorded_at:new Date().toISOString()});clearStatus();await refresh();document.dispatchEvent(new CustomEvent("fieldora:dossier-workspace-changed",{detail:{module_id:moduleId,project_id:projectId,dossier_id:record.id}}));return true}catch(error){report(error,"Dossier could not be saved.");return false}}
 async function linkEvidence(){const dossierId=state.selectedDossierId,mediaId=q("dossier-evidence-select")?.value||"";if(!dossierId||!mediaId)return;try{const service=dataService();if(!service?.linkEvidence)throw new Error("Dossier data service is unavailable.");await service.linkEvidence(dossierId,mediaId);await refreshEvidence();document.dispatchEvent(new CustomEvent("fieldora:dossier-evidence-changed",{detail:{module_id:moduleId,dossier_id:dossierId,media_id:mediaId,action:"linked"}}))}catch(error){q("dossier-evidence-status").textContent=error?.message||"Evidence could not be linked."}}
 async function unlinkEvidence(mediaId){const dossierId=state.selectedDossierId;if(!dossierId||!mediaId)return;try{const service=dataService();if(!service?.unlinkEvidence)throw new Error("Dossier data service is unavailable.");await service.unlinkEvidence(dossierId,mediaId);await refreshEvidence();document.dispatchEvent(new CustomEvent("fieldora:dossier-evidence-changed",{detail:{module_id:moduleId,dossier_id:dossierId,media_id:mediaId,action:"unlinked"}}))}catch(error){q("dossier-evidence-status").textContent=error?.message||"Evidence could not be unlinked."}}
 function mount(){if(state.mounted)return;const page=q("page-dossiers");if(!page)return;state.mounted=true;state.controller=new AbortController();ensureEvidenceSurface();syncProjectContext();q("dossier-refresh")?.addEventListener("click",refresh,{signal:state.controller.signal});q("dossier-save")?.addEventListener("click",save,{signal:state.controller.signal});q("dossier-workspace-list")?.addEventListener("click",event=>{const row=event.target.closest("[data-dossier-workspace]");if(row)renderDetail(row.dataset.dossierWorkspace)},{signal:state.controller.signal});q("dossier-evidence-link")?.addEventListener("click",linkEvidence,{signal:state.controller.signal});q("dossier-evidence-list")?.addEventListener("click",event=>{const button=event.target.closest("[data-dossier-evidence-unlink]");if(button)unlinkEvidence(button.dataset.dossierEvidenceUnlink)},{signal:state.controller.signal});refresh()}
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false}
 document.addEventListener("fieldora:project-context-changed",()=>{if(state.mounted)syncProjectContext()});
 document.addEventListener("fieldora:contract-registered",event=>{if(state.mounted&&event.detail?.contract==="projects.context.select")syncProjectContext()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraDossiers=Object.freeze({mount,unmount,refresh,save,currentProject:()=>currentProject()});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_dossier_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Dossier service boundary and workspace module exactly once."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = response.body
    if _DOSSIER_DATA_SERVICE_PATCH not in body:
        body += _DOSSIER_DATA_SERVICE_PATCH
    if _DOSSIER_MODULE_PATCH not in body:
        body += _DOSSIER_MODULE_PATCH
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)


class DossierModuleWebApiMixin:
    """Compose the independently mountable Dossier browser module."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_dossier_module_response(target, response)
