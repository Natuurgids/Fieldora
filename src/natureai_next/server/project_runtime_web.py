"""Governed Project child-work and existing-evidence controls for managed web."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit
import json

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.media_links import new_association


_PROJECT_RUNTIME_WEB_PATCH = bytes(
    r"""

/* WEB-058: selected Project child work and pre-existing Library evidence. */
(()=>{
 if(window.__fieldoraProjectRuntimeWired)return;window.__fieldoraProjectRuntimeWired=true;
 const q=id=>document.getElementById(id),page=q("page-projects");if(!page)return;
 const top=page.querySelector(".top"),button=document.createElement("button");
 button.id="portfolio-project-work";button.type="button";button.textContent="Project work & evidence";
 button.dataset.fieldoraAuthorizationHidden="true";top?.appendChild(button);
 const panel=document.createElement("section");panel.id="portfolio-project-runtime";panel.className="card section";panel.hidden=true;
 panel.innerHTML='<h2>Project work & evidence</h2><p class="muted">Add child work or associate governed Library evidence. Linking keeps the existing evidence identity and provenance.</p><div class="form-grid"><label>Task title<input id="portfolio-project-task-title"></label><label>Existing Library evidence<select id="portfolio-project-evidence"><option value="">Choose evidence…</option></select></label></div><div class="actions section"><button id="portfolio-project-task-add" class="primary" type="button">Add task</button><button id="portfolio-project-evidence-link" type="button">Link evidence</button><button id="portfolio-project-runtime-close" type="button">Close</button></div><p id="portfolio-project-runtime-message" class="status"></p><div id="portfolio-project-linked-evidence" class="muted"></div>';
 const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(panel);else page.appendChild(panel);
 const msg=(text,error=false)=>{const n=q("portfolio-project-runtime-message");n.textContent=text;n.classList.toggle("error",error)};
 async function authority(){
  button.dataset.fieldoraAuthorizationHidden="true";const id=selectedProject||"";if(!id)return false;
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(id)}/capabilities`,{purpose:"research"});const allowed=caps?.actions?.edit===true;button.dataset.fieldoraAuthorizationHidden=allowed?"false":"true";if(!allowed)panel.hidden=true;return allowed}catch(_e){panel.hidden=true;return false}
 }
 async function evidenceOptions(){
  const select=q("portfolio-project-evidence");select.innerHTML='<option value="">Choose evidence…</option>';
  const library=(await api("/api/v1/media?limit=200",{purpose:"research"})).items||[];
  library.forEach(item=>{const option=document.createElement("option");option.value=item.media_id;option.textContent=`${item.mime_type||"evidence"} · ${String(item.media_id).slice(0,12)}`;select.appendChild(option)});
 }
 async function linkedEvidence(){
  const host=q("portfolio-project-linked-evidence"),id=selectedProject||"";if(!id){host.textContent="";return}
  const linked=(await api(`/api/v1/media?project_id=${encodeURIComponent(id)}&limit=200`,{purpose:"research"})).items||[];
  host.textContent=linked.length?`Linked evidence: ${linked.map(item=>String(item.media_id).slice(0,12)).join(", ")}`:"No evidence linked yet.";
 }
 button.onclick=async()=>{if(!await authority())return;panel.hidden=false;msg("");try{await evidenceOptions();await linkedEvidence()}catch(e){msg(e.message,true)}};
 q("portfolio-project-runtime-close").onclick=()=>{panel.hidden=true;msg("")};
 q("portfolio-project-task-add").onclick=async()=>{
  const projectId=selectedProject||"",title=q("portfolio-project-task-title").value.trim();if(!projectId||!title)return msg("Choose a project and enter a task title.",true);
  try{await api("/api/v1/tasks",{method:"POST",purpose:"research",body:JSON.stringify({project_id:projectId,title})});q("portfolio-project-task-title").value="";msg("Task added to the selected project.")}catch(e){msg(e.message,true)}
 };
 q("portfolio-project-evidence-link").onclick=async()=>{
  const projectId=selectedProject||"",mediaId=q("portfolio-project-evidence").value;if(!projectId||!mediaId)return msg("Choose existing Library evidence.",true);
  try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mediaId})});msg("Existing Library evidence linked without changing its identity.");await linkedEvidence()}catch(e){msg(e.message,true)}
 };
 document.addEventListener("click",event=>{if(event.target.closest?.("[data-project-tree]"))setTimeout(authority,0)});
 const tree=q("project-cockpit-tree");if(tree)new MutationObserver(()=>setTimeout(authority,0)).observe(tree,{childList:true,subtree:true});
 authority();
})();
""",
    "utf-8",
)


class ProjectRuntimeWebApiMixin:
    """Link existing Library evidence to Projects without changing evidence identity."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        project_id = self._media_link_project(route.path)
        if project_id and method == "POST":
            routed_headers = dict(headers)
            cookie_token = _session_cookie(routed_headers.get("cookie", ""))
            if not routed_headers.get("authorization") and cookie_token:
                routed_headers["authorization"] = f"Bearer {cookie_token}"
            response = self._link_existing_media(project_id, routed_headers, body)
            browser_session = getattr(self, "_browser_session_response", None)
            if callable(browser_session):
                response = browser_session(
                    method, route.path, routed_headers, cookie_token, response
                )
        else:
            response = super().dispatch(method, target, headers, body)
        return self._patch_project_runtime_response(target, response)

    @staticmethod
    def _media_link_project(path: str) -> str:
        prefix = "/api/v1/projects/"
        suffix = "/media-links"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return ""
        value = path[len(prefix) : -len(suffix)].strip("/")
        return unquote(value).strip()

    def _link_existing_media(
        self, project_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        media = getattr(self, "_media", None)
        if media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        try:
            record = json.loads(body)
            if not isinstance(record, dict):
                raise ValueError
            media_id = str(record["media_id"]).strip()
            if not media_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        project = self._project_for_organization(identity.organization_id, project_id)
        if project is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        edit = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        )
        if not edit.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        evidence = media.record(media_id)
        if evidence is None or evidence.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        view = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view",
                "asset",
                media_id,
                identity.organization_id,
                "",
                purpose,
            )
        )
        link = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "link",
                "asset",
                media_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        )
        if not view.allowed or not link.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        already_linked = media_id in set(
            media.associations.linked_media_ids(
                identity.organization_id, "project", project_id
            )
        )
        media.associations.link(
            new_association(
                media_id=media_id,
                organization_id=identity.organization_id,
                association_type="project",
                target_id=project_id,
                purpose=purpose,
                linked_by=identity.identity_id,
            )
        )
        return ApiResponse.json(
            200 if already_linked else 201,
            {"media_id": media_id, "project_id": project_id, "replayed": already_linked},
        )

    @staticmethod
    def _patch_project_runtime_response(target: str, response: ApiResponse) -> ApiResponse:
        if (
            urlsplit(target).path != "/app.js"
            or response.status != 200
            or _PROJECT_RUNTIME_WEB_PATCH in response.body
        ):
            return response
        return ApiResponse(
            response.status,
            response.body + _PROJECT_RUNTIME_WEB_PATCH,
            response.content_type,
            response.headers,
        )
