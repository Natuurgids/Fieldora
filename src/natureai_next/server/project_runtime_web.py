"""Governed Project child-work and existing-evidence controls for managed web."""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.media_links import new_association

_PROJECT_RUNTIME_WEB_PATCH = bytes(
    r"""

/* WEB-032/058: selected Project hierarchy, child work and pre-existing Library evidence. */
(()=>{
 if(window.__fieldoraProjectRuntimeWired)return;window.__fieldoraProjectRuntimeWired=true;
 const q=id=>document.getElementById(id),page=q("page-projects");if(!page)return;
 const top=page.querySelector(".top"),button=document.createElement("button");
 button.id="portfolio-project-work";button.type="button";button.textContent="Project hierarchy & evidence";
 button.dataset.fieldoraAuthorizationHidden="true";top?.appendChild(button);
 const panel=document.createElement("section");panel.id="portfolio-project-runtime";panel.className="card section";panel.hidden=true;
 panel.innerHTML='<h2>Project hierarchy</h2><p class="muted">Create governed Project work with explicit parentage. Linking Library evidence keeps its existing identity and provenance.</p><div class="actions section"><button id="portfolio-project-phase-add" type="button">New phase</button><button id="portfolio-project-task-add" class="primary" type="button">New task</button><button id="portfolio-project-subtask-add" type="button">New subtask</button><button id="portfolio-project-sprint-add" type="button">New sprint</button><button id="portfolio-project-allocation-add" type="button">New allocation</button></div><div class="form-grid"><label>Name / title<input id="portfolio-project-task-title" placeholder="Work item name"></label><label>Parent task<select id="portfolio-project-parent-task"><option value="">No parent</option></select></label><label>Phase<select id="portfolio-project-phase"><option value="">No phase</option></select></label><label>Start date<input id="portfolio-project-work-start" type="date"></label><label>End / due date<input id="portfolio-project-work-end" type="date"></label><label>Allocation user<input id="portfolio-project-allocation-user" placeholder="User ID"></label></div><div class="section"><strong>Current hierarchy</strong><div id="portfolio-project-hierarchy" class="muted">Choose a project.</div></div><hr><h3>Existing Library evidence</h3><div class="form-grid"><label>Existing Library evidence<select id="portfolio-project-evidence"><option value="">Choose evidence…</option></select></label></div><div class="actions section"><button id="portfolio-project-evidence-link" type="button">Link evidence</button><button id="portfolio-project-runtime-close" type="button">Close</button></div><p id="portfolio-project-runtime-message" class="status"></p><div id="portfolio-project-linked-evidence" class="muted"></div>';
 const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(panel);else page.appendChild(panel);
 const msg=(text,error=false)=>{const n=q("portfolio-project-runtime-message");n.textContent=text;n.classList.toggle("error",error)};
 let phaseItems=[],taskItems=[],sprintItems=[],allocationItems=[];
 const selected=()=>selectedProject||"";
 const projectItems=items=>items.filter(item=>String(item.project_id||"")===selected());
 async function authority(){
  button.dataset.fieldoraAuthorizationHidden="true";const id=selected();if(!id)return false;
  try{const caps=await api(`/api/v1/projects/${encodeURIComponent(id)}/capabilities`,{purpose:"research"});const allowed=caps?.actions?.edit===true;button.dataset.fieldoraAuthorizationHidden=allowed?"false":"true";if(!allowed)panel.hidden=true;return allowed}catch(_e){panel.hidden=true;return false}
 }
 function addOption(select,item,label){const node=document.createElement("option");node.value=String(item.id||"");node.textContent=label;select.appendChild(node)}
 function refreshSelectors(){
  const parent=q("portfolio-project-parent-task"),phase=q("portfolio-project-phase");parent.innerHTML='<option value="">No parent</option>';phase.innerHTML='<option value="">No phase</option>';
  projectItems(taskItems).forEach(item=>addOption(parent,item,item.title||item.name||String(item.id).slice(0,12)));
  projectItems(phaseItems).forEach(item=>addOption(phase,item,item.name||String(item.id).slice(0,12)));
 }
 function renderHierarchy(){
  const host=q("portfolio-project-hierarchy"),phases=projectItems(phaseItems),tasks=projectItems(taskItems),sprints=projectItems(sprintItems),allocations=projectItems(allocationItems);
  host.replaceChildren();
  if(!phases.length&&!tasks.length&&!sprints.length&&!allocations.length){host.textContent="No phases, tasks, sprints or allocations yet.";return}
  const roots=tasks.filter(item=>!item.parent_task_id),children=parent=>tasks.filter(item=>String(item.parent_task_id||"")===String(parent.id||""));
  const taskNode=(item,depth=0)=>{const wrap=document.createElement("div");wrap.dataset.projectWork=String(item.id||"");wrap.style.paddingLeft=`${depth*18}px`;wrap.textContent=`${depth?"↳ ":""}${item.title||item.name||"Task"}${item.status?` · ${item.status}`:""}`;children(item).forEach(child=>wrap.appendChild(taskNode(child,depth+1)));return wrap};
  phases.forEach(phase=>{const section=document.createElement("div");section.dataset.projectPhase=String(phase.id||"");const heading=document.createElement("strong");heading.textContent=`Phase · ${phase.name||phase.id}`;section.appendChild(heading);roots.filter(item=>String(item.phase_id||"")===String(phase.id||"")).forEach(item=>section.appendChild(taskNode(item)));host.appendChild(section)});
  roots.filter(item=>!item.phase_id).forEach(item=>host.appendChild(taskNode(item)));
  sprints.forEach(item=>{const line=document.createElement("div");line.textContent=`Sprint · ${item.name||item.id}`;host.appendChild(line)});
  allocations.forEach(item=>{const line=document.createElement("div");line.textContent=`Allocation · ${item.user_id||"user"}${item.hours_per_week?` · ${item.hours_per_week} h/week`:""}`;host.appendChild(line)});
 }
 async function childData(){
  const [phases,tasks,sprints,allocations]=await Promise.all([api("/api/v1/phases",{purpose:"research"}),api("/api/v1/tasks",{purpose:"research"}),api("/api/v1/sprints",{purpose:"research"}),api("/api/v1/allocations",{purpose:"research"})]);
  phaseItems=phases.items||[];taskItems=tasks.items||[];sprintItems=sprints.items||[];allocationItems=allocations.items||[];refreshSelectors();renderHierarchy();
 }
 async function evidenceOptions(){
  const select=q("portfolio-project-evidence");select.innerHTML='<option value="">Choose evidence…</option>';
  const library=(await api("/api/v1/media?limit=200",{purpose:"research"})).items||[];
  library.forEach(item=>{const node=document.createElement("option");node.value=item.media_id;node.textContent=`${item.mime_type||"evidence"} · ${String(item.media_id).slice(0,12)}`;select.appendChild(node)});
 }
 async function linkedEvidence(){
  const host=q("portfolio-project-linked-evidence"),id=selected();if(!id){host.textContent="";return}
  const linked=(await api(`/api/v1/media?project_id=${encodeURIComponent(id)}&limit=200`,{purpose:"research"})).items||[];
  host.textContent=linked.length?`Linked evidence: ${linked.map(item=>String(item.media_id).slice(0,12)).join(", ")}`:"No evidence linked yet.";
 }
 async function createChild(kind,extra={}){
  const projectId=selected(),title=q("portfolio-project-task-title").value.trim();if(!projectId||!title)return msg("Choose a project and enter a name or title.",true);
  const start=q("portfolio-project-work-start").value,end=q("portfolio-project-work-end").value,phaseId=q("portfolio-project-phase").value,parentId=q("portfolio-project-parent-task").value;
  const routes={phase:"phases",task:"tasks",sprint:"sprints",allocation:"allocations"},body={project_id:projectId,name:title,title,start_date:start,due_date:end,end_date:end,phase_id:phaseId||undefined,...extra};
  if(kind==="task"&&parentId&&!body.parent_task_id)body.parent_task_id=parentId;
  if(kind==="allocation"){body.user_id=q("portfolio-project-allocation-user").value.trim();body.hours_per_week=0;if(!body.user_id||!start)return msg("Allocation requires a user ID and start date.",true)}
  try{await api(`/api/v1/${routes[kind]}`,{method:"POST",purpose:"research",body:JSON.stringify(body)});q("portfolio-project-task-title").value="";await childData();msg(`${kind[0].toUpperCase()+kind.slice(1)} created in the selected project.`)}catch(e){msg(e.message,true)}
 }
 button.onclick=async()=>{if(!await authority())return;panel.hidden=false;msg("");try{await Promise.all([childData(),evidenceOptions(),linkedEvidence()])}catch(e){msg(e.message,true)}};
 q("portfolio-project-runtime-close").onclick=()=>{panel.hidden=true;msg("")};
 q("portfolio-project-phase-add").onclick=()=>createChild("phase");
 q("portfolio-project-task-add").onclick=()=>createChild("task",{parent_task_id:""});
 q("portfolio-project-subtask-add").onclick=()=>{const parent=q("portfolio-project-parent-task").value;if(!parent)return msg("Choose the parent task for the new subtask.",true);return createChild("task",{parent_task_id:parent})};
 q("portfolio-project-sprint-add").onclick=()=>createChild("sprint");
 q("portfolio-project-allocation-add").onclick=()=>createChild("allocation");
 q("portfolio-project-evidence-link").onclick=async()=>{
  const projectId=selected(),mediaId=q("portfolio-project-evidence").value;if(!projectId||!mediaId)return msg("Choose existing Library evidence.",true);
  try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mediaId})});msg("Existing Library evidence linked without changing its identity.");await linkedEvidence()}catch(e){msg(e.message,true)}
 };
 document.addEventListener("click",event=>{if(event.target.closest?.("[data-project-tree]"))setTimeout(()=>{authority();if(!panel.hidden)childData().catch(e=>msg(e.message,true))},0)});
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
