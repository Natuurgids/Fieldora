"""Module-owned existing-evidence linking for Projects/Core.

The browser selects existing Library evidence and requests a governed Project
association. The server independently verifies Project edit, evidence view and
link authorization and preserves the evidence identity/provenance boundary.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_EVIDENCE_ACTIONS_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-EVIDENCE-ACTIONS-MODULE: Projects/Core governed evidence linking. */
(()=>{
 if(window.__fieldoraProjectEvidenceActionsWired)return;window.__fieldoraProjectEvidenceActionsWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",canEdit:false};
 function message(text,error=false){const node=q("project-core-evidence-link-message");if(node){node.textContent=text||"";node.classList.toggle("error",Boolean(error))}}
 function emitError(error,fallback){const text=error?.message||fallback;message(text,true);document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}))}
 function ensureSurface(){
  const page=q("page-projects"),top=page?.querySelector(".top");if(!page||!top)return false;
  let button=q("project-core-evidence-link");
  if(!button){button=document.createElement("button");button.id="project-core-evidence-link";button.type="button";button.textContent="Link Library evidence";button.dataset.fieldoraAuthorizationHidden="true";top.appendChild(button)}
  if(!q("project-core-evidence-link-panel")){
   const panel=document.createElement("section");panel.id="project-core-evidence-link-panel";panel.className="card section";panel.hidden=true;
   panel.innerHTML='<h2>Link Library evidence</h2><p class="muted">Link an existing governed Library item without changing its evidence identity or provenance.</p><label>Existing Library evidence<select id="project-core-evidence-select"><option value="">Choose evidence…</option></select></label><div class="actions section"><button id="project-core-evidence-link-save" class="primary" type="button">Link evidence</button><button id="project-core-evidence-link-cancel" type="button">Cancel</button></div><p id="project-core-evidence-link-message" class="status"></p>';
   const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(panel);else page.appendChild(panel);
  }
  return true;
 }
 async function refreshAuthority(){
  const button=q("project-core-evidence-link");if(button)button.dataset.fieldoraAuthorizationHidden="true";state.canEdit=false;
  if(!state.projectId)return;
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});state.canEdit=caps?.actions?.edit===true;if(button)button.dataset.fieldoraAuthorizationHidden=state.canEdit?"false":"true"}catch(error){emitError(error,"Project permissions could not be loaded.")}
 }
 async function loadOptions(){
  const select=q("project-core-evidence-select");if(!select)return;select.innerHTML='<option value="">Choose evidence…</option>';
  const result=await api("/api/v1/media?limit=200",{purpose:"research"});
  (result.items||[]).forEach(item=>{const option=document.createElement("option");option.value=item.media_id;option.textContent=`${item.mime_type||"evidence"} · ${String(item.filename||item.name||item.media_id).slice(0,48)}`;select.appendChild(option)});
 }
 async function openPanel(){
  if(!state.projectId||!state.canEdit)return;const panel=q("project-core-evidence-link-panel");if(!panel)return;panel.hidden=false;message("");
  try{await loadOptions()}catch(error){emitError(error,"Library evidence could not be loaded.")}
 }
 function closePanel(){const panel=q("project-core-evidence-link-panel");if(panel)panel.hidden=true;message("")}
 async function linkEvidence(){
  const mediaId=q("project-core-evidence-select")?.value||"";if(!state.projectId||!mediaId)return message("Choose existing Library evidence.",true);
  try{
   message("Linking evidence…");
   await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mediaId})});
   message("Existing Library evidence linked without changing its identity.");
   document.dispatchEvent(new CustomEvent("fieldora:project-evidence-changed",{detail:{module_id:moduleId,project_id:state.projectId,media_id:mediaId}}));
  }catch(error){emitError(error,"Evidence could not be linked to this project.")}
 }
 function mount(){
  if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;
  q("project-core-evidence-link")?.addEventListener("click",openPanel,{signal});q("project-core-evidence-link-save")?.addEventListener("click",linkEvidence,{signal});q("project-core-evidence-link-cancel")?.addEventListener("click",closePanel,{signal});
  state.projectId=window.FieldoraProjects?.currentProject?.()||"";refreshAuthority();
 }
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;closePanel()}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";closePanel();refreshAuthority()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectEvidenceActions=Object.freeze({mount,unmount,openPanel,refreshAuthority});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_project_evidence_actions_module_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Projects/Core evidence action adapter exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_EVIDENCE_ACTIONS_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_EVIDENCE_ACTIONS_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectEvidenceActionsModuleWebApiMixin:
    """Compose the independently owned Project evidence-linking controls."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_evidence_actions_module_response(target, response)
