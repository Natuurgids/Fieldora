"""Bounded Projects-to-Research browser integration for managed web.

Research owns the cross-module entry point. Projects publishes project context and
a replaceable cockpit-extension contract; this adapter consumes those contracts
and hands the selected Project to Research without owning Projects DOM details.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_RESEARCH_INTEGRATION_PATCH = bytes(
    r"""

/* WEB-PROJECT-RESEARCH-INTEGRATION: bounded Projects -> Research navigation. */
(()=>{
 if(window.__fieldoraProjectResearchIntegrationWired)return;window.__fieldoraProjectResearchIntegrationWired=true;
 const ownerModule="research.dossiers",entryKey="research.project.open";
 const state={projectId:""};
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 const projectToolbar=()=>window.FieldoraModuleContracts?.resolve?.("projects.toolbar.extend")||null;
 function report(error,fallback){
  const text=error?.message||fallback;
  document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:ownerModule,error:String(text)}}));
 }
 function currentProject(){return projectContext()?.current?.()||state.projectId||""}
 function updateEntry(){return projectToolbar()?.setEnabled?.(entryKey,Boolean(currentProject()))??false}
 function ensureEntry(){
  const toolbar=projectToolbar();if(!toolbar?.upsert)return false;
  toolbar.upsert({key:entryKey,label:"Open research",ownerModule,action:"research.project.open",enabled:Boolean(currentProject()),activate:openSelectedProject});return true;
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
 function editResearchRecord(kind){
  q("record-editor").hidden=false;q("record-editor").dataset.kind=kind;q("record-editor-title").textContent=`New ${kind}`;
  q("record-project").value=kind==="project"?"":currentProject();
 }
 async function exportCurrentProject(){
  const pid=currentProject();if(!pid)return status("project-job-status","Select a project.",true);
  try{
   const job=await api("/api/v1/jobs",{method:"POST",purpose:"research",body:JSON.stringify({job_type:"export_project",project_id:pid,include_library_references:true})});
   status("project-job-status",`Export queued · job ${job.job_id}`);q("job-id").value=job.job_id;
  }catch(error){status("project-job-status",error.message,true)}
 }
 if(typeof editRecord==="function")editRecord=editResearchRecord;
 if(typeof exportProject==="function")exportProject=exportCurrentProject;
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";ensureEntry();updateEntry()});
 document.addEventListener("fieldora:contract-registered",event=>{const name=event.detail?.contract;if(name==="projects.context.select"){state.projectId=currentProject();updateEntry()}else if(name==="projects.toolbar.extend")ensureEntry()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===ownerModule)applyResearchProject().catch(error=>report(error,"Research project context could not be applied."))});
 window.FieldoraProjectResearchIntegration=Object.freeze({openSelectedProject,applyResearchProject,currentProject,editResearchRecord,exportCurrentProject});
 ensureEntry();if(window.FieldoraModules?.current?.()?.module_id===ownerModule)applyResearchProject().catch(()=>{});
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