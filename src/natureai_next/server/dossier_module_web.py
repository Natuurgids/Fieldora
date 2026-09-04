"""Module-owned Dossier workspace for managed web.

This adapter establishes an independently mountable Dossier owner before the
legacy `/dossiers` wiring is retired. It consumes Project context through the
public `projects.context.select` contract and deliberately does not acquire the
Project list contract or ambient `projects` state.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_DOSSIER_MODULE_PATCH = bytes(
    r"""

/* WEB-DOSSIER-MODULE: bounded dossier workspace owner. */
(()=>{
 if(window.__fieldoraDossierModuleWired)return;window.__fieldoraDossierModuleWired=true;
 const moduleId="dossiers.workspace",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",dossiers:[],reviews:[],identityId:""};
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const nameOf=record=>record?.name||record?.title||record?.id||"Record";
 function context(){return window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null}
 function currentProject(){return String(context()?.current?.()||state.projectId||"")}
 function report(error,fallback){const text=error?.message||fallback,node=q("dossier-status");if(node){node.textContent=text;node.style.color="var(--danger)"}document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}))}
 function clearStatus(){const node=q("dossier-status");if(node){node.textContent="";node.style.color=""}}
 function syncProjectContext(){state.projectId=currentProject();const selector=q("dossier-project");if(selector&&state.projectId&&selector.value!==state.projectId)selector.value=state.projectId;return state.projectId}
 function render(){const host=q("dossier-workspace-list");if(!host)return;const children=new Map();for(const dossier of state.dossiers){const parent=dossier.parent_dossier_id||"";if(!children.has(parent))children.set(parent,[]);children.get(parent).push(dossier)}const rows=[];const walk=(parent,depth)=>{for(const dossier of children.get(parent)||[]){rows.push(`<button type="button" class="row" data-dossier-workspace="${esc(dossier.id)}"><strong>${" ".repeat(depth)}${depth?"↳ ":""}${esc(nameOf(dossier))}</strong><span>${esc(dossier.dossier_type||"dossier")}</span><span>${esc(dossier.review_status||dossier.status||"draft")}</span></button>`);walk(dossier.id,depth+1)}};walk("",0);host.innerHTML=rows.join("")||'<p class="empty">No dossiers.</p>'}
 function renderDetail(id){const dossier=state.dossiers.find(item=>item.id===id),host=q("dossier-workspace-detail");if(!host)return;const reviews=state.reviews.filter(item=>item.dossier_id===dossier?.id);host.innerHTML=`<h3>${esc(nameOf(dossier||{}))}</h3><pre>${esc(JSON.stringify(dossier||{},null,2))}</pre><h4>Review history</h4><pre>${esc(JSON.stringify(reviews,null,2))}</pre>`}
 async function refresh(){try{const [dossiers,reviews]=await Promise.all([api("/api/v1/dossiers"),api("/api/v1/dossier-reviews")]);state.dossiers=dossiers.items||[];state.reviews=reviews.items||[];render();clearStatus();return state.dossiers.slice()}catch(error){state.dossiers=[];state.reviews=[];render();report(error,"Dossiers could not be loaded.");return []}}
 async function ensureIdentity(){if(state.identityId)return state.identityId;try{const identity=await api("/api/v1/me");state.identityId=String(identity.identity_id||"")}catch(error){report(error,"Identity could not be loaded.")}return state.identityId}
 async function save(){const projectId=syncProjectContext();if(!projectId){report(null,"Select a Project before creating a dossier.");return false}const ownerId=q("dossier-owner")?.value||await ensureIdentity();const record={id:crypto.randomUUID(),project_id:projectId,name:q("dossier-name")?.value||"",description:q("dossier-description")?.value||"",dossier_type:q("dossier-type")?.value||"",parent_dossier_id:q("dossier-parent")?.value||"",owner_id:ownerId,reviewer_id:q("dossier-reviewer")?.value||"",review_status:q("dossier-review-status")?.value||"",status:"active"};try{await api("/api/v1/dossiers",{method:"POST",body:JSON.stringify(record)});const remark=q("dossier-remark")?.value||"";if(remark)await api("/api/v1/dossier-reviews",{method:"POST",body:JSON.stringify({id:crypto.randomUUID(),project_id:projectId,dossier_id:record.id,reviewer_id:record.reviewer_id,remark,status:record.review_status,recorded_at:new Date().toISOString()})});clearStatus();await refresh();document.dispatchEvent(new CustomEvent("fieldora:dossier-workspace-changed",{detail:{module_id:moduleId,project_id:projectId,dossier_id:record.id}}));return true}catch(error){report(error,"Dossier could not be saved.");return false}}
 function mount(){if(state.mounted)return;const page=q("page-dossiers");if(!page)return;state.mounted=true;state.controller=new AbortController();syncProjectContext();q("dossier-refresh")?.addEventListener("click",refresh,{signal:state.controller.signal});q("dossier-save")?.addEventListener("click",save,{signal:state.controller.signal});q("dossier-workspace-list")?.addEventListener("click",event=>{const row=event.target.closest("[data-dossier-workspace]");if(row)renderDetail(row.dataset.dossierWorkspace)},{signal:state.controller.signal});refresh()}
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
    """Append the Dossier workspace module exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _DOSSIER_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _DOSSIER_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class DossierModuleWebApiMixin:
    """Compose the independently mountable Dossier browser module."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_dossier_module_response(target, response)
