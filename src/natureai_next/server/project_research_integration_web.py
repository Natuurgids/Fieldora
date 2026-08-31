"""Bounded Projects-to-Research browser integration for managed web.

Research owns the cross-module entry point. Projects/Core only publishes project
context; this adapter consumes that public context and hands the selected Project
to the Research workspace through its public browser contract.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_RESEARCH_INTEGRATION_PATCH = bytes(
    r"""

/* WEB-PROJECT-RESEARCH-INTEGRATION: bounded Projects -> Research navigation. */
(()=>{
 if(window.__fieldoraProjectResearchIntegrationWired)return;window.__fieldoraProjectResearchIntegrationWired=true;
 const ownerModule="research.dossiers",projectModule="projects.core",q=id=>document.getElementById(id);
 const state={projectId:"",projectMounted:false};
 function report(error,fallback){
  const text=error?.message||fallback;
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:ownerModule,error:String(text)}}));
 }
 function currentProject(){return state.projectId||window.FieldoraProjects?.currentProject?.()||""}
 function updateEntry(){const button=q("project-open-research");if(button)button.disabled=!currentProject()}
 function removeEntry(){q("project-open-research")?.remove()}
 function ensureEntry(){
  const toolbar=q("project-desktop-cockpit")?.querySelector(".cockpit-center .cockpit-toolbar");if(!toolbar)return false;
  let button=q("project-open-research");
  if(!button){button=document.createElement("button");button.id="project-open-research";button.type="button";button.textContent="Open research";button.dataset.fieldoraOwnerModule=ownerModule;button.dataset.fieldoraAction="research.project.open";button.addEventListener("click",openSelectedProject);toolbar.appendChild(button)}
  updateEntry();return true;
 }
 async function applyResearchProject(){
  const pid=currentProject();if(!pid)return false;
  const bridge=window.FieldoraResearchRecords;
  if(!bridge?.openProject)throw new Error("Research workspace integration is unavailable.");
  await bridge.openProject(pid);return true;
 }
 async function openSelectedProject(){
  const pid=currentProject();if(!pid){report(null,"Select a project before opening Research.");return}
  try{
   const target=window.FieldoraModules?.navigate?.("/research","project-research-integration","push");
   if(!target)throw new Error("Research workspace is unavailable.");
   await applyResearchProject();
  }catch(error){report(error,"Research could not be opened for this project.")}
 }
 function mountProjectEntry(){state.projectMounted=true;state.projectId=window.FieldoraProjects?.currentProject?.()||state.projectId;ensureEntry()}
 function unmountProjectEntry(){state.projectMounted=false;removeEntry()}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";if(state.projectMounted)ensureEntry();updateEntry()});
 document.addEventListener("fieldora:module-mount",event=>{const id=event.detail?.module?.module_id;if(id===projectModule)mountProjectEntry();else if(id===ownerModule)applyResearchProject().catch(error=>report(error,"Research project context could not be applied."))});
 document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===projectModule)unmountProjectEntry()});
 window.FieldoraProjectResearchIntegration=Object.freeze({openSelectedProject,applyResearchProject,currentProject});
 const active=window.FieldoraModules?.current?.()?.module_id;if(active===projectModule)mountProjectEntry();else if(active===ownerModule)applyResearchProject().catch(()=>{});
})();
""",
    "utf-8",
)


def patch_project_research_integration_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the Research-owned Project integration exactly once."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_RESEARCH_INTEGRATION_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_RESEARCH_INTEGRATION_PATCH,
        response.content_type,
        response.headers,
    )


class ProjectResearchIntegrationWebApiMixin:
    """Compose the bounded Projects-to-Research browser integration."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_project_research_integration_response(target, response)
