"""Bounded Projects-to-Capacity browser integration for managed web.

Capacity owns the cross-module entry point. Projects/Core only publishes project
context; this adapter consumes that contract and hands the selected Project to the
Capacity module without owning Capacity rendering or persistence.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_CAPACITY_INTEGRATION_PATCH = bytes(
    r"""

/* WEB-PROJECT-CAPACITY-INTEGRATION: bounded Projects -> Capacity navigation. */
(()=>{
 if(window.__fieldoraProjectCapacityIntegrationWired)return;window.__fieldoraProjectCapacityIntegrationWired=true;
 const ownerModule="capacity",projectModule="projects.core",q=id=>document.getElementById(id);
 const state={projectId:"",projectMounted:false};
 function report(error,fallback){const text=error?.message||fallback;document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:ownerModule,error:String(text)}}))}
 function currentProject(){return state.projectId||window.FieldoraProjects?.currentProject?.()||""}
 function updateEntry(){const button=q("project-open-capacity");if(button)button.disabled=!currentProject()}
 function removeEntry(){q("project-open-capacity")?.remove()}
 function ensureEntry(){
  const toolbar=q("project-desktop-cockpit")?.querySelector(".cockpit-center .cockpit-toolbar");if(!toolbar)return false;
  let button=q("project-open-capacity");
  if(!button){button=document.createElement("button");button.id="project-open-capacity";button.type="button";button.textContent="Open capacity";button.dataset.fieldoraOwnerModule=ownerModule;button.dataset.fieldoraAction="capacity.project.open";button.addEventListener("click",openSelectedProject);toolbar.appendChild(button)}
  updateEntry();return true;
 }
 async function applyCapacityProject(){const pid=currentProject();if(!pid)return false;const bridge=window.FieldoraCapacity;if(!bridge?.openProject)throw new Error("Capacity workspace integration is unavailable.");await bridge.openProject(pid);return true}
 async function openSelectedProject(){
  const pid=currentProject();if(!pid){report(null,"Select a project before opening Capacity.");return}
  try{const target=window.FieldoraModules?.navigate?.("/capacity","project-capacity-integration","push");if(!target)throw new Error("Capacity workspace is unavailable.");await applyCapacityProject()}
  catch(error){report(error,"Capacity could not be opened for this project.")}
 }
 function mountProjectEntry(){state.projectMounted=true;state.projectId=window.FieldoraProjects?.currentProject?.()||state.projectId;ensureEntry()}
 function unmountProjectEntry(){state.projectMounted=false;removeEntry()}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";if(state.projectMounted)ensureEntry();updateEntry()});
 document.addEventListener("fieldora:module-mount",event=>{const id=event.detail?.module?.module_id;if(id===projectModule)mountProjectEntry();else if(id===ownerModule)applyCapacityProject().catch(error=>report(error,"Capacity project context could not be applied."))});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===projectModule)unmountProjectEntry()});
 window.FieldoraProjectCapacityIntegration=Object.freeze({openSelectedProject,applyCapacityProject,currentProject});
 const active=window.FieldoraModules?.current?.()?.module_id;if(active===projectModule)mountProjectEntry();else if(active===ownerModule)applyCapacityProject().catch(()=>{});
})();
""",
    "utf-8",
)


def patch_project_capacity_integration_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Capacity-owned Project integration exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_CAPACITY_INTEGRATION_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_CAPACITY_INTEGRATION_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectCapacityIntegrationWebApiMixin:
    """Compose bounded Projects-to-Capacity browser integration."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_capacity_integration_response(target, response)
