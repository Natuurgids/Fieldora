"""Revision-safe Project lifecycle controls for the managed Fieldora web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_LIFECYCLE_WEB_PATCH = bytes(
    r"""

/* Fieldora Project lifecycle: selected-project edit, status and archive. */
(()=>{
 if(window.__fieldoraProjectLifecycleWired)return;window.__fieldoraProjectLifecycleWired=true;
 const q=id=>document.getElementById(id);
 const page=q("page-projects");if(!page)return;
 const top=page.querySelector(".top");
 const editButton=document.createElement("button");
 editButton.id="portfolio-edit-project";editButton.type="button";editButton.textContent="Edit selected project";
 editButton.dataset.fieldoraAuthorizationHidden="true";top?.appendChild(editButton);
 const editor=document.createElement("section");editor.id="portfolio-project-lifecycle-editor";editor.className="card section";editor.hidden=true;
 editor.innerHTML='<h2>Project lifecycle</h2><p id="portfolio-project-lifecycle-revision" class="muted"></p><div class="form-grid"><label>Name<input id="portfolio-project-lifecycle-name"></label><label>Status<select id="portfolio-project-lifecycle-status"><option value="active">active</option><option value="cancelled">cancelled</option><option value="archived">archived</option></select></label><label>Start date<input id="portfolio-project-lifecycle-start" type="date"></label><label>Due date<input id="portfolio-project-lifecycle-due" type="date"></label><label>Budget<input id="portfolio-project-lifecycle-budget" type="number" min="0" step="0.01"></label><label>Currency<input id="portfolio-project-lifecycle-currency" maxlength="3"></label></div><label class="section">Description<textarea id="portfolio-project-lifecycle-description"></textarea></label><div class="actions section"><button id="portfolio-project-lifecycle-save" class="primary" type="button">Save details</button><button id="portfolio-project-lifecycle-apply-status" type="button">Apply status</button><button id="portfolio-project-lifecycle-archive" type="button">Archive project</button><button id="portfolio-project-lifecycle-cancel" type="button">Close</button></div><p id="portfolio-project-lifecycle-message" class="status"></p>';
 const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(editor);else page.appendChild(editor);
 let editingId="";
 const projectById=id=>(projects||[]).find(project=>project.id===id)||null;
 const message=(text,error=false)=>{const node=q("portfolio-project-lifecycle-message");node.textContent=text;node.classList.toggle("error",error)};
 function fill(project){
  if(!project)return;
  editingId=project.id;q("portfolio-project-lifecycle-name").value=project.name||"";q("portfolio-project-lifecycle-description").value=project.description||"";q("portfolio-project-lifecycle-status").value=project.status||"active";q("portfolio-project-lifecycle-start").value=project.start_date||"";q("portfolio-project-lifecycle-due").value=project.due_date||"";q("portfolio-project-lifecycle-budget").value=Number(project.budget||0);q("portfolio-project-lifecycle-currency").value=project.currency||"EUR";q("portfolio-project-lifecycle-revision").textContent=`Server revision ${project.revision}`;
 }
 async function refreshAuthority(){
  editButton.dataset.fieldoraAuthorizationHidden="true";
  const id=selectedProject||"";if(!id)return;
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(id)}/capabilities`,{purpose:"research"});editButton.dataset.fieldoraAuthorizationHidden=caps?.actions?.edit===true?"false":"true"}catch(_error){editButton.dataset.fieldoraAuthorizationHidden="true"}
 }
 async function reloadProjects(){
  projects=(await api("/api/v1/projects",{purpose:"research"})).items||[];projectOptions();await loadPortfolio();return projectById(editingId||selectedProject)
 }
 async function conflict(){
  const current=await reloadProjects();if(current)fill(current);editor.hidden=false;message("Project changed on the server. Latest values reloaded; review them before saving again.",true)
 }
 async function mutate(path,body,success){
  try{await api(path,{method:"PATCH",purpose:"research",body:JSON.stringify(body)});const current=await reloadProjects();if(current)fill(current);message(success);await refreshAuthority();return true}catch(error){if(error.message==="revision_conflict"){await conflict();return false}message(error.message,true);return false}
 }
 editButton.onclick=()=>{const project=projectById(selectedProject);if(!project)return;fill(project);message("");editor.hidden=false;q("portfolio-project-lifecycle-name").focus()};
 q("portfolio-project-lifecycle-cancel").onclick=()=>{editor.hidden=true;message("")};
 q("portfolio-project-lifecycle-save").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  const name=q("portfolio-project-lifecycle-name").value.trim();if(!name)return message("Project name is required.",true);
  const budget=Number(q("portfolio-project-lifecycle-budget").value||0);if(!Number.isFinite(budget)||budget<0)return message("Budget must be zero or greater.",true);
  await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}`,{expected_revision:project.revision,name,description:q("portfolio-project-lifecycle-description").value.trim(),start_date:q("portfolio-project-lifecycle-start").value,due_date:q("portfolio-project-lifecycle-due").value,budget,currency:(q("portfolio-project-lifecycle-currency").value.trim()||"EUR").toUpperCase()},"Project details saved.")
 };
 q("portfolio-project-lifecycle-apply-status").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}/status`,{expected_revision:project.revision,status:q("portfolio-project-lifecycle-status").value},"Project status updated.")
 };
 q("portfolio-project-lifecycle-archive").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  const ok=await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}/archive`,{expected_revision:project.revision},"Project archived.");if(ok)editor.hidden=true
 };
 document.addEventListener("click",event=>{if(event.target.closest?.("[data-project-tree]"))setTimeout(refreshAuthority,0)});
 const tree=q("project-cockpit-tree");if(tree)new MutationObserver(()=>setTimeout(refreshAuthority,0)).observe(tree,{childList:true,subtree:true});
 refreshAuthority();
})();
""",
    "utf-8",
)


def patch_project_lifecycle_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append revision-safe Project lifecycle controls once to managed app.js."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_LIFECYCLE_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_LIFECYCLE_WEB_PATCH,
        response.content_type,
        response.headers,
    )
