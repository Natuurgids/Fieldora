"""Module-owned Capacity project-allocation view for managed web.

The legacy Capacity page still contains schedules/absence compatibility UI. This
adapter owns only the Project-context allocation slice and consumes the governed
Project hierarchy allocation API rather than duplicating Capacity persistence.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


_CAPACITY_MODULE_PATCH = bytes(
    r"""

/* WEB-CAPACITY-MODULE: bounded project allocation view. */
(()=>{
 if(window.__fieldoraCapacityModuleWired)return;window.__fieldoraCapacityModuleWired=true;
 const moduleId="capacity",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",allocations:[]};
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function report(error,fallback){
  const text=error?.message||fallback,node=q("capacity-project-status");if(node){node.textContent=text;node.classList.add("error")}
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}));
 }
 function ensureSurface(){
  const page=q("page-capacity");if(!page)return false;
  let host=q("capacity-project-context");
  if(!host){host=document.createElement("section");host.id="capacity-project-context";host.className="card section";host.innerHTML='<div class="top"><div><h2>Selected project allocations</h2><p class="muted" id="capacity-project-label">Open a project from Projects to inspect its governed allocations.</p></div><button type="button" id="capacity-project-refresh" data-fieldora-action="capacity.project.allocations.view">Refresh allocations</button></div><div id="capacity-project-allocation-list" class="list"></div><p id="capacity-project-status" class="status"></p>';page.querySelector(".top")?.after(host)}
  return true;
 }
 function render(){
  if(!ensureSurface())return;const host=q("capacity-project-allocation-list"),label=q("capacity-project-label");if(!host)return;
  if(label)label.textContent=state.projectId?`Project ${state.projectId}`:"Open a project from Projects to inspect its governed allocations.";
  if(!state.projectId){host.innerHTML='<div class="empty">No project context selected.</div>';return}
  host.innerHTML=state.allocations.length?state.allocations.map(item=>`<div class="row" data-capacity-allocation="${esc(item.id)}"><strong>${esc(item.user_id||item.id)}</strong><span>${esc(item.role||"Allocation")}</span><span>${esc(item.hours_per_week??0)} h/week · ${esc(item.allocation_percent??0)}%</span><span>${esc(item.start_date||"")}${item.end_date?` → ${esc(item.end_date)}`:""}</span></div>`).join(""):'<div class="empty">No governed allocations for this project.</div>';
 }
 async function refresh(){
  render();if(!state.projectId)return;
  try{const result=await api(`/api/v1/allocations?project_id=${encodeURIComponent(state.projectId)}`,{purpose:"research"});state.allocations=result.items||[];render();const node=q("capacity-project-status");if(node){node.textContent="";node.classList.remove("error")}}
  catch(error){state.allocations=[];render();report(error,"Project allocations could not be loaded.")}
 }
 async function openProject(projectId){state.projectId=String(projectId||"");await refresh();return state.projectId}
 function mount(){if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();q("capacity-project-refresh")?.addEventListener("click",refresh,{signal:state.controller.signal});render();if(state.projectId)refresh()}
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false}
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraCapacity=Object.freeze({mount,unmount,openProject,refresh,currentProject:()=>state.projectId});
 if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
""",
    "utf-8",
)


def patch_capacity_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Capacity-owned Project allocation adapter exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _CAPACITY_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _CAPACITY_MODULE_PATCH,
        response.content_type,
        response.headers,
    )


class CapacityModuleWebApiMixin:
    """Compose the bounded Capacity browser module."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_capacity_module_response(target, response)
