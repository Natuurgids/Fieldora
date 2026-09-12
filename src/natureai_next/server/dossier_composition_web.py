"""Managed-web adapter for explicit Dossier master composition."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_DOSSIER_COMPOSITION_PATCH = bytes(
    r"""

/* WEB-DOSSIER-COMPOSITION: explicit master-dossier relationship projection. */
(()=>{
 if(window.__fieldoraDossierCompositionWired)return;window.__fieldoraDossierCompositionWired=true;
 const moduleId="dossiers.workspace",contractName="dossiers.composition.service",q=id=>document.getElementById(id);
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 async function load(masterId){const id=String(masterId||"").trim();if(!id)throw new Error("Dossier identifier is required.");return api(`/api/v1/dossiers/${encodeURIComponent(id)}/composition`,{purpose:"research"})}
 async function add(masterId,childId){const master=String(masterId||"").trim(),child=String(childId||"").trim();if(!master||!child)throw new Error("Master and child dossier identifiers are required.");return api(`/api/v1/dossiers/${encodeURIComponent(master)}/composition`,{method:"POST",purpose:"research",body:JSON.stringify({child_dossier_id:child})})}
 async function remove(masterId,childId){const master=String(masterId||"").trim(),child=String(childId||"").trim();if(!master||!child)throw new Error("Master and child dossier identifiers are required.");return api(`/api/v1/dossiers/${encodeURIComponent(master)}/composition/${encodeURIComponent(child)}`,{method:"DELETE",purpose:"research"})}
 const implementation=Object.freeze({load,add,remove});
 function register(){const contracts=window.FieldoraModuleContracts;if(!contracts)return false;const current=contracts.resolve(contractName);if(current)return current===implementation;contracts.register(contractName,moduleId,implementation);return true}
 register();document.addEventListener("fieldora:contracts-ready",register,{once:true});

 const state={mounted:false,controller:null,selectedId:"",projection:null};
 function service(){return window.FieldoraModuleContracts?.resolve?.(contractName)||null}
 function ensureSurface(){const page=q("page-dossiers");if(!page||q("dossier-composition-panel"))return;const panel=document.createElement("section");panel.id="dossier-composition-panel";panel.className="card section";panel.hidden=true;panel.innerHTML='<h2>Master dossier composition</h2><p class="muted">A master dossier references independent dossiers. Child dossiers keep their own Project, ownership, review state, and evidence.</p><label>Available dossier<select id="dossier-composition-select"><option value="">Choose dossier…</option></select></label><div class="actions section"><button id="dossier-composition-add" class="primary" type="button">Add dossier to master</button></div><div id="dossier-composition-children"></div><p id="dossier-composition-status" class="status"></p>';const anchor=q("dossier-evidence-panel")||q("dossier-lifecycle-panel")||q("dossier-workspace-detail");anchor?.after(panel)}
 function hide(){const panel=q("dossier-composition-panel");if(panel)panel.hidden=true;state.projection=null}
 function render(projection){state.projection=projection||null;const panel=q("dossier-composition-panel"),select=q("dossier-composition-select"),host=q("dossier-composition-children");if(!panel||!select||!host)return;if(!projection?.is_master){hide();return}panel.hidden=false;select.innerHTML='<option value="">Choose dossier…</option>';for(const item of projection.available_children||[]){const option=document.createElement("option");option.value=String(item.id||"");option.textContent=String(item.name||item.title||item.id||"Dossier");select.appendChild(option)}const children=projection.children||[];host.innerHTML=children.length?children.map(item=>`<div class="row" data-dossier-composition-child="${esc(item.id)}"><strong>${esc(item.name||item.title||item.id)}</strong><span>${esc(item.project_id||"Independent")}</span><span>${esc(item.description||"")}</span><button type="button" data-dossier-composition-remove="${esc(item.id)}">Remove</button></div>`).join(""):'<p class="empty">No child dossiers.</p>';q("dossier-composition-status").textContent=""}
 async function refresh(id=state.selectedId){state.selectedId=String(id||"").trim();if(!state.selectedId){hide();return}try{const implementation=service();if(!implementation?.load)throw new Error("Dossier composition service is unavailable.");const result=await implementation.load(state.selectedId);render(result?.item)}catch(error){hide();const node=q("dossier-composition-status");if(node)node.textContent=error?.message||"Dossier composition could not be loaded."}}
 async function addChild(){const childId=q("dossier-composition-select")?.value||"";if(!state.selectedId||!childId)return;try{const implementation=service();if(!implementation?.add)throw new Error("Dossier composition service is unavailable.");const result=await implementation.add(state.selectedId,childId);render(result?.item);document.dispatchEvent(new CustomEvent("fieldora:dossier-composition-changed",{detail:{module_id:moduleId,master_dossier_id:state.selectedId,child_dossier_id:childId,action:"linked"}}))}catch(error){const node=q("dossier-composition-status");if(node)node.textContent=error?.message||"Child dossier could not be added."}}
 async function removeChild(childId){if(!state.selectedId||!childId)return;try{const implementation=service();if(!implementation?.remove)throw new Error("Dossier composition service is unavailable.");const result=await implementation.remove(state.selectedId,childId);render(result?.item);document.dispatchEvent(new CustomEvent("fieldora:dossier-composition-changed",{detail:{module_id:moduleId,master_dossier_id:state.selectedId,child_dossier_id:childId,action:"unlinked"}}))}catch(error){const node=q("dossier-composition-status");if(node)node.textContent=error?.message||"Child dossier could not be removed."}}
 function mount(){if(state.mounted)return;const page=q("page-dossiers");if(!page)return;state.mounted=true;state.controller=new AbortController();ensureSurface();q("dossier-workspace-list")?.addEventListener("click",event=>{const row=event.target.closest("[data-dossier-workspace]");if(row)refresh(row.dataset.dossierWorkspace)},{signal:state.controller.signal});q("dossier-composition-add")?.addEventListener("click",addChild,{signal:state.controller.signal});q("dossier-composition-children")?.addEventListener("click",event=>{const button=event.target.closest("[data-dossier-composition-remove]");if(button)removeChild(button.dataset.dossierCompositionRemove)},{signal:state.controller.signal})}
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;state.selectedId="";hide()}
 document.addEventListener("fieldora:dossier-workspace-changed",event=>{if(state.mounted&&event.detail?.dossier_id)refresh(event.detail.dossier_id)});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_dossier_composition_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append explicit master-composition transport and presentation wiring once."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    if _DOSSIER_COMPOSITION_PATCH in response.body:
        return response
    return ApiResponse(
        response.status,
        response.body + _DOSSIER_COMPOSITION_PATCH,
        response.content_type,
        response.headers,
    )
