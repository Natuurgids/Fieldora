"""Bounded Projects-to-Capacity browser integration for managed web.

Capacity owns the cross-module entry point. Projects publishes project context and
a replaceable cockpit-extension contract; this adapter consumes those contracts
and hands the selected Project to Capacity without owning Projects DOM details.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_CAPACITY_INTEGRATION_PATCH = bytes(
    r"""

/* WEB-PROJECT-CAPACITY-INTEGRATION: bounded Projects -> Capacity navigation. */
(()=>{
 if(window.__fieldoraProjectCapacityIntegrationWired)return;window.__fieldoraProjectCapacityIntegrationWired=true;
 const ownerModule="capacity",entryKey="capacity.project.open";
 const state={projectId:""};
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 const projectToolbar=()=>window.FieldoraModuleContracts?.resolve?.("projects.toolbar.extend")||null;
 function report(error,fallback){const text=error?.message||fallback;document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:ownerModule,error:String(text)}}))}
 function currentProject(){return projectContext()?.current?.()||state.projectId||""}
 function updateEntry(){return projectToolbar()?.setEnabled?.(entryKey,Boolean(currentProject()))??false}
 function ensureEntry(){
  const toolbar=projectToolbar();if(!toolbar?.upsert)return false;
  toolbar.upsert({key:entryKey,label:"Open capacity",ownerModule,action:"capacity.project.open",enabled:Boolean(currentProject()),activate:openSelectedProject});return true;
 }
 async function applyCapacityProject(){const pid=currentProject();if(!pid)return false;const bridge=window.FieldoraCapacity;if(!bridge?.openProject)throw new Error("Capacity workspace integration is unavailable.");await bridge.openProject(pid);return true}
 async function openSelectedProject(){
  const pid=currentProject();if(!pid){report(null,"Select a project before opening Capacity.");return}
  try{const target=window.FieldoraModules?.navigate?.("/capacity","project-capacity-integration","push");if(!target)throw new Error("Capacity workspace is unavailable.");await applyCapacityProject()}
  catch(error){report(error,"Capacity could not be opened for this project.")}
 }
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";ensureEntry();updateEntry()});
 document.addEventListener("fieldora:contract-registered",event=>{const name=event.detail?.contract;if(name==="projects.context.select"){state.projectId=currentProject();updateEntry()}else if(name==="projects.toolbar.extend")ensureEntry()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===ownerModule)applyCapacityProject().catch(error=>report(error,"Capacity project context could not be applied."))});
 window.FieldoraProjectCapacityIntegration=Object.freeze({openSelectedProject,applyCapacityProject,currentProject});
 ensureEntry();if(window.FieldoraModules?.current?.()?.module_id===ownerModule)applyCapacityProject().catch(()=>{});
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
