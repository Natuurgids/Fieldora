"""Projects-owned browser provider for project-context selection."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_CONTEXT_PROVIDER_PATCH = bytes(
    r"""

/* WEB-PROJECT-CONTEXT-PROVIDER: Projects-owned context selection contract. */
(()=>{
 if(window.__fieldoraProjectContextProviderWired)return;window.__fieldoraProjectContextProviderWired=true;
 const moduleId="projects.core",contractName="projects.context.select";
 const owner=()=>window.FieldoraProjects||null;
 const implementation=Object.freeze({
  select:id=>{const projects=owner();if(!projects?.selectProject)throw new Error("Projects context owner is unavailable.");return projects.selectProject(id)},
  current:()=>owner()?.currentProject?.()||""
 });
 function register(){
  const contracts=window.FieldoraModuleContracts;if(!contracts)return false;
  const current=contracts.resolve(contractName);
  if(current)return current===implementation;
  contracts.register(contractName,moduleId,implementation);return true;
 }
 register();
 document.addEventListener('fieldora:contracts-ready',register,{once:true});
 window.FieldoraProjectContext=implementation;
})();
""",
    "utf-8",
)


def patch_project_context_provider_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Projects context provider after module and contract runtime wiring."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-PROJECT-CORE-MODULE" not in response.body
        or b"WEB-MODULE-CONTRACT-RUNTIME" not in response.body
        or _PROJECT_CONTEXT_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_CONTEXT_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
