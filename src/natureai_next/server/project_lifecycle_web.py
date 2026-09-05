"""Revision-safe Project lifecycle controls for the managed Fieldora web client.

WEB-031 keeps Project status semantics in the authoritative managed Project service.
This module is transport/presentation only: PBAC, validation, audit and revision
conflicts remain server-side invariants.
"""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie

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
 editor.innerHTML='<h2>Project lifecycle</h2><p id="portfolio-project-lifecycle-revision" class="muted"></p><div class="form-grid"><label>Name<input id="portfolio-project-lifecycle-name"></label><label>Status<select id="portfolio-project-lifecycle-status"><option value="active">active</option><option value="cancelled">cancelled</option><option value="archived">archived</option></select></label><label>Start date<input id="portfolio-project-lifecycle-start" type="date"></label><label>Due date<input id="portfolio-project-lifecycle-due" type="date"></label><label>Budget<input id="portfolio-project-lifecycle-budget" type="number" min="0" step="0.01"></label><label>Currency<input id="portfolio-project-lifecycle-currency" maxlength="8"></label></div><label class="section">Description<textarea id="portfolio-project-lifecycle-description"></textarea></label><div class="actions section"><button id="portfolio-project-lifecycle-save" class="primary" type="button">Save details</button><button id="portfolio-project-lifecycle-apply-status" type="button">Apply status</button><button id="portfolio-project-lifecycle-archive" type="button">Archive project</button><button id="portfolio-project-lifecycle-cancel" type="button">Close</button></div><p id="portfolio-project-lifecycle-message" class="status"></p>';
 const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(editor);else page.appendChild(editor);
 let editingId="";
 const projectById=id=>(projects||[]).find(project=>String(project.id)===String(id))||null;
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
  projects=(await api("/api/v1/projects",{purpose:"research"})).items||[];if(typeof projectOptions==="function")projectOptions();await loadPortfolio();return projectById(editingId||selectedProject)
 }
 async function rawConflict(){
  const current=await reloadProjects();if(current)fill(current);editor.hidden=false;message("Project changed on the server. Latest values reloaded; review them before saving again.",true)
 }
 async function mutate(path,body,success){
  try{await api(path,{method:"PATCH",purpose:"research",body:JSON.stringify(body)});const current=await reloadProjects();if(current)fill(current);message(success);await refreshAuthority();return true}catch(error){if((error?.code||error?.message)==="revision_conflict"){await rawConflict();return false}message(error?.message||"Project update failed.",true);return false}
 }
 editButton.onclick=()=>{const project=projectById(selectedProject);if(!project)return;fill(project);message("");editor.hidden=false;q("portfolio-project-lifecycle-name").focus()};
 q("portfolio-project-lifecycle-cancel").onclick=()=>{editor.hidden=true;message("")};
 q("portfolio-project-lifecycle-save").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  const name=q("portfolio-project-lifecycle-name").value.trim();if(!name)return message("Project name is required.",true);
  const budget=Number(q("portfolio-project-lifecycle-budget").value||0);if(!Number.isFinite(budget)||budget<0)return message("Budget must be zero or greater.",true);
  await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}`,{expected_revision:project.revision,name,description:q("portfolio-project-lifecycle-description").value.trim(),start_date:q("portfolio-project-lifecycle-start").value,due_date:q("portfolio-project-lifecycle-due").value,budget,currency:q("portfolio-project-lifecycle-currency").value.trim()||"EUR"},"Project details saved.")
 };
 q("portfolio-project-lifecycle-apply-status").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}/status`,{expected_revision:project.revision,status:q("portfolio-project-lifecycle-status").value},"Project status updated.")
 };
 q("portfolio-project-lifecycle-archive").onclick=async()=>{
  const project=projectById(editingId);if(!project)return;
  const ok=await mutate(`/api/v1/projects/${encodeURIComponent(editingId)}/archive`,{expected_revision:project.revision},"Project archived.");if(ok)editor.hidden=true
 };
 document.addEventListener("click",event=>{if(event.target.closest?.("[data-project-tree]")||event.target.closest?.('[data-portfolio-id][data-kind="project"]'))setTimeout(refreshAuthority,0)});
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


class ProjectLifecycleWebApiMixin:
    """Expose managed status transitions and append the WEB-031 browser controls."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        project_id = self._status_project_id(route.path)
        service = getattr(self, "_project_management", None)
        if method == "PATCH" and project_id and hasattr(service, "set_project_status"):
            routed_headers = dict(headers)
            cookie_token = _session_cookie(routed_headers.get("cookie", ""))
            if not routed_headers.get("authorization") and cookie_token:
                routed_headers["authorization"] = f"Bearer {cookie_token}"
            response = self._set_managed_project_status(
                project_id, routed_headers, body
            )
            browser_session = getattr(self, "_browser_session_response", None)
            if callable(browser_session):
                response = browser_session(
                    method, route.path, routed_headers, cookie_token, response
                )
        else:
            response = super().dispatch(method, target, headers, body)
        return patch_project_lifecycle_response(target, response)

    @staticmethod
    def _status_project_id(path: str) -> str:
        prefix = "/api/v1/projects/"
        suffix = "/status"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return ""
        project_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        return project_id if project_id and "/" not in project_id else ""

    def _set_managed_project_status(
        self, project_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )
        try:
            record = json.loads(body)
            if not isinstance(record, dict) or "expected_revision" not in record:
                raise ValueError
            expected_revision = int(record["expected_revision"])
            status = str(record["status"]).strip().lower()
            if not status:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        current = self._project_for_organization(identity.organization_id, project_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        try:
            self._project_management.set_project_status(
                project_id,
                status,
                organization_id=identity.organization_id,
                actor_id=identity.identity_id,
                expected_revision=expected_revision,
            )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except (TypeError, ValueError) as exc:
            if "revision conflict" in str(exc).lower():
                latest = self._project_for_organization(
                    identity.organization_id, project_id
                )
                return ApiResponse.json(
                    409,
                    {
                        "error": "revision_conflict",
                        "current": (
                            None if latest is None else self._project_item(latest)
                        ),
                    },
                )
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        item = self._project_for_organization(identity.organization_id, project_id)
        assert item is not None
        return ApiResponse.json(
            200, {"item": self._project_item(item), "revision": item.revision}
        )
