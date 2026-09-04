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
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 const canonicalProjectId=()=>String(projectContext()?.current?.()||"");
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function report(error,fallback){
  const text=error?.message||fallback,node=q("capacity-project-status");if(node){node.textContent=text;node.classList.add("error")}
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}));
 }
 function clearStatus(){const node=q("capacity-project-status");if(node){node.textContent="";node.classList.remove("error")}}
 function retireLegacyAllocationCreate(){
  const type=q("capacity-type"),option=type?.querySelector('option[value="allocation"]');if(!option)return;
  if(type.value==="allocation")type.value=type.querySelector('option:not([value="allocation"])')?.value||"";option.remove();
 }
 function ensureSurface(){
  const page=q("page-capacity");if(!page)return false;
  let host=q("capacity-project-context");
  if(!host){host=document.createElement("section");host.id="capacity-project-context";host.className="card section";host.innerHTML='<div class="top"><div><h2>Selected project allocations</h2><p class="muted" id="capacity-project-label">Open a project from Projects to inspect its governed allocations.</p></div><button type="button" id="capacity-project-refresh" data-fieldora-action="capacity.project.allocations.view">Refresh allocations</button></div><form id="capacity-project-allocation-create" class="form-grid section" data-fieldora-action="capacity.project.allocations.create"><label>User<input id="capacity-allocation-user" autocomplete="off" required></label><label>Start date<input id="capacity-allocation-start" type="date" required></label><label>End date<input id="capacity-allocation-end" type="date"></label><label>Hours / week<input id="capacity-allocation-hours" type="number" min="0" step="0.25" value="0"></label><label>Allocation %<input id="capacity-allocation-percent" type="number" min="0" step="1" value="0"></label><label>Role<input id="capacity-allocation-role" autocomplete="off"></label><div class="actions"><button type="submit" class="primary">Create allocation</button></div></form><div id="capacity-project-allocation-list" class="list"></div><p id="capacity-project-status" class="status"></p>';page.querySelector(".top")?.after(host)}
  return true;
 }
 function render(){
  if(!ensureSurface())return;const host=q("capacity-project-allocation-list"),label=q("capacity-project-label"),form=q("capacity-project-allocation-create");if(!host)return;
  if(label)label.textContent=state.projectId?`Project ${state.projectId}`:"Open a project from Projects to inspect its governed allocations.";
  if(form)form.querySelectorAll("input,button").forEach(node=>{node.disabled=!state.projectId});
  if(!state.projectId){host.innerHTML='<div class="empty">No project context selected.</div>';return}
  host.innerHTML=state.allocations.length?state.allocations.map(item=>`<div class="row" data-capacity-allocation="${esc(item.id)}"><strong>${esc(item.user_id||item.id)}</strong><span>${esc(item.role||"Allocation")}</span><span>${esc(item.hours_per_week??0)} h/week · ${esc(item.allocation_percent??0)}%</span><span>${esc(item.start_date||"")}${item.end_date?` → ${esc(item.end_date)}`:""}</span></div>`).join(""):'<div class="empty">No governed allocations for this project.</div>';
 }
 async function refresh(){
  render();if(!state.projectId)return;
  try{const result=await api(`/api/v1/allocations?project_id=${encodeURIComponent(state.projectId)}`,{purpose:"research"});state.allocations=result.items||[];render();clearStatus()}
  catch(error){state.allocations=[];render();report(error,"Project allocations could not be loaded.")}
 }
 async function createAllocation(event){
  event?.preventDefault?.();const projectId=canonicalProjectId();if(!projectId){report(null,"Select a project before creating an allocation.");return false}
  const userId=q("capacity-allocation-user")?.value.trim()||"",startDate=q("capacity-allocation-start")?.value||"";
  if(!userId||!startDate){report(null,"User and start date are required.");return false}
  const record={project_id:projectId,user_id:userId,start_date:startDate,end_date:q("capacity-allocation-end")?.value||"",hours_per_week:Number(q("capacity-allocation-hours")?.value||0),allocation_percent:Number(q("capacity-allocation-percent")?.value||0),role:q("capacity-allocation-role")?.value.trim()||""};
  try{
   await api("/api/v1/allocations",{method:"POST",purpose:"research",body:JSON.stringify(record)});state.projectId=projectId;q("capacity-project-allocation-create")?.reset();await refresh();document.dispatchEvent(new CustomEvent("fieldora:capacity-allocations-changed",{detail:{module_id:moduleId,project_id:projectId}}));return true
  }catch(error){report(error,"Project allocation could not be created.");return false}
 }
 async function openProject(projectId){state.projectId=String(projectId||"");document.dispatchEvent(new CustomEvent("fieldora:capacity-project-changed",{detail:{module_id:moduleId,project_id:state.projectId}}));await refresh();return state.projectId}
 function mount(){if(state.mounted)return;retireLegacyAllocationCreate();if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();q("capacity-project-refresh")?.addEventListener("click",refresh,{signal:state.controller.signal});q("capacity-project-allocation-create")?.addEventListener("submit",createAllocation,{signal:state.controller.signal});render();if(state.projectId)refresh()}
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false}
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraCapacity=Object.freeze({mount,unmount,openProject,refresh,createAllocation,currentProject:()=>state.projectId});
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
