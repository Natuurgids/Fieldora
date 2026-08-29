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

/* WEB-032/058: governed Project hierarchy, child work, and Library evidence. */
(()=>{
 if(window.__fieldoraProjectRuntimeWired)return;window.__fieldoraProjectRuntimeWired=true;
 const q=id=>document.getElementById(id),page=q("page-projects");if(!page)return;
 const top=page.querySelector(".top"),button=document.createElement("button");
 button.id="portfolio-project-work";button.type="button";button.textContent="Project work & evidence";
 button.dataset.fieldoraAuthorizationHidden="true";top?.appendChild(button);
 const panel=document.createElement("section");panel.id="portfolio-project-runtime";panel.className="card section";panel.hidden=true;
 panel.innerHTML='<h2>Project work & evidence</h2><p class="muted">Create governed Project hierarchy and associate existing Library evidence. Select a phase or task below to create work in that context.</p><div class="form-grid"><label>Phase name<input id="portfolio-project-phase-name"></label><label>Task title<input id="portfolio-project-task-title"></label><label>Sprint name<input id="portfolio-project-sprint-name"></label><label>Allocation user<input id="portfolio-project-allocation-user"></label><label>Allocation start<input id="portfolio-project-allocation-start" type="date"></label><label>Existing Library evidence<select id="portfolio-project-evidence"><option value="">Choose evidence…</option></select></label></div><div class="actions section"><button id="portfolio-project-phase-add" class="primary" type="button">New phase</button><button id="portfolio-project-task-add" class="primary" type="button">New task</button><button id="portfolio-project-subtask-add" type="button" disabled>New subtask</button><button id="portfolio-project-sprint-add" type="button">New sprint</button><button id="portfolio-project-allocation-add" type="button">New allocation</button><button id="portfolio-project-evidence-link" type="button">Link evidence</button><button id="portfolio-project-runtime-close" type="button">Close</button></div><p id="portfolio-project-work-context" class="muted">No child selected.</p><p id="portfolio-project-runtime-message" class="status"></p><div class="section"><h3>Hierarchy</h3><div id="portfolio-project-hierarchy" class="stack muted">Select a Project to load its hierarchy.</div></div><div id="portfolio-project-linked-evidence" class="muted"></div>';
 const cockpit=q("project-desktop-cockpit");if(cockpit)cockpit.before(panel);else page.appendChild(panel);
 let selectedParentTask="",selectedPhase="";
 const msg=(text,error=false)=>{const n=q("portfolio-project-runtime-message");n.textContent=text;n.classList.toggle("error",error)};
 function context(){const n=q("portfolio-project-work-context");n.textContent=selectedParentTask?`Selected parent task: ${selectedParentTask.slice(0,12)}`:selectedPhase?`Selected phase: ${selectedPhase.slice(0,12)}`:"No child selected.";q("portfolio-project-subtask-add").disabled=!selectedParentTask}
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
 function hierarchyButton(label,kind,id,depth=0){const row=document.createElement("button");row.type="button";row.className="tree-row";row.style.paddingLeft=`${8+depth*20}px`;row.textContent=label;row.dataset.projectWorkKind=kind;row.dataset.projectWorkId=id;row.onclick=()=>{if(kind==="task"){selectedParentTask=id;selectedPhase=""}else if(kind==="phase"){selectedPhase=id;selectedParentTask=""}else{selectedPhase="";selectedParentTask=""}context()};return row}
 async function hierarchy(){
  const host=q("portfolio-project-hierarchy"),id=selectedProject||"";host.replaceChildren();if(!id){host.textContent="Select a Project to load its hierarchy.";return}
  const data=await api(`/api/v1/projects/${encodeURIComponent(id)}/work-hierarchy`,{purpose:"research"}),phases=data.phases||[],tasks=data.tasks||[],sprints=data.sprints||[],allocations=data.allocations||[];
  const phaseTasks=new Map(phases.map(p=>[p.id,[]])),root=[];tasks.forEach(t=>{if(t.phase_id&&phaseTasks.has(t.phase_id))phaseTasks.get(t.phase_id).push(t);else root.push(t)});
  phases.forEach(p=>{host.appendChild(hierarchyButton(`Phase · ${p.name}`,"phase",p.id));(phaseTasks.get(p.id)||[]).forEach(t=>host.appendChild(hierarchyButton(`${t.parent_task_id?"Subtask":"Task"} · ${t.title||t.name}`,"task",t.id,t.parent_task_id?2:1)))});
  root.forEach(t=>host.appendChild(hierarchyButton(`${t.parent_task_id?"Subtask":"Task"} · ${t.title||t.name}`,"task",t.id,t.parent_task_id?1:0)));
  sprints.forEach(s=>host.appendChild(hierarchyButton(`Sprint · ${s.name}`,"sprint",s.id)));
  allocations.forEach(a=>host.appendChild(hierarchyButton(`Allocation · ${a.user_id}`,"allocation",a.id)));
  if(!host.childElementCount)host.textContent="No phases, tasks, sprints or allocations yet.";
 }
 async function refresh(){await hierarchy();await linkedEvidence()}
 button.onclick=async()=>{if(!await authority())return;panel.hidden=false;selectedParentTask="";selectedPhase="";context();msg("");try{await evidenceOptions();await refresh()}catch(e){msg(e.message,true)}};
 q("portfolio-project-runtime-close").onclick=()=>{panel.hidden=true;msg("")};
 q("portfolio-project-phase-add").onclick=async()=>{const projectId=selectedProject||"",name=q("portfolio-project-phase-name").value.trim();if(!projectId||!name)return msg("Choose a project and enter a phase name.",true);try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/phases`,{method:"POST",purpose:"research",body:JSON.stringify({name})});q("portfolio-project-phase-name").value="";msg("Phase added to the selected project.");await hierarchy()}catch(e){msg(e.message,true)}};
 async function addTask(asSubtask){const projectId=selectedProject||"",title=q("portfolio-project-task-title").value.trim();if(!projectId||!title)return msg("Choose a project and enter a task title.",true);if(asSubtask&&!selectedParentTask)return msg("Select a parent task in the hierarchy first.",true);try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/tasks`,{method:"POST",purpose:"research",body:JSON.stringify({title,parent_task_id:asSubtask?selectedParentTask:"",phase_id:asSubtask?"":selectedPhase})});q("portfolio-project-task-title").value="";msg(asSubtask?"Subtask added to the selected task.":"Task added to the selected project.");await hierarchy()}catch(e){msg(e.message,true)}}
 q("portfolio-project-task-add").onclick=()=>addTask(false);q("portfolio-project-subtask-add").onclick=()=>addTask(true);
 q("portfolio-project-sprint-add").onclick=async()=>{const projectId=selectedProject||"",name=q("portfolio-project-sprint-name").value.trim();if(!projectId||!name)return msg("Choose a project and enter a sprint name.",true);try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/sprints`,{method:"POST",purpose:"research",body:JSON.stringify({name})});q("portfolio-project-sprint-name").value="";msg("Sprint added to the selected project.");await hierarchy()}catch(e){msg(e.message,true)}};
 q("portfolio-project-allocation-add").onclick=async()=>{const projectId=selectedProject||"",user_id=q("portfolio-project-allocation-user").value.trim(),start_date=q("portfolio-project-allocation-start").value;if(!projectId||!user_id||!start_date)return msg("Choose a project, allocation user and start date.",true);try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/allocations`,{method:"POST",purpose:"research",body:JSON.stringify({user_id,start_date,phase_id:selectedPhase})});q("portfolio-project-allocation-user").value="";msg("Allocation added to the selected project.");await hierarchy()}catch(e){msg(e.message,true)}};
 q("portfolio-project-evidence-link").onclick=async()=>{const projectId=selectedProject||"",mediaId=q("portfolio-project-evidence").value;if(!projectId||!mediaId)return msg("Choose existing Library evidence.",true);try{await api(`/api/v1/projects/${encodeURIComponent(projectId)}/media-links`,{method:"POST",purpose:"research",body:JSON.stringify({media_id:mediaId})});msg("Existing Library evidence linked without changing its identity.");await linkedEvidence()}catch(e){msg(e.message,true)}};
 document.addEventListener("click",event=>{if(event.target.closest?.("[data-project-tree]")){selectedParentTask="";selectedPhase="";context();setTimeout(authority,0)}});
 const tree=q("project-cockpit-tree");if(tree)new MutationObserver(()=>setTimeout(authority,0)).observe(tree,{childList:true,subtree:true});
 authority();
})();
""",
    "utf-8",
)


class ProjectRuntimeWebApiMixin:
    """Govern Project child work and existing Library evidence through shared services."""

    _WORK_KINDS = frozenset({"phases", "tasks", "sprints", "allocations"})

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        project_id = self._media_link_project(route.path)
        work_route = self._project_work_route(route.path)
        if (project_id and method == "POST") or work_route is not None:
            routed_headers = dict(headers)
            cookie_token = _session_cookie(routed_headers.get("cookie", ""))
            if not routed_headers.get("authorization") and cookie_token:
                routed_headers["authorization"] = f"Bearer {cookie_token}"
            if project_id and method == "POST":
                response = self._link_existing_media(project_id, routed_headers, body)
            elif work_route is not None:
                work_project, kind = work_route
                response = self._project_work_response(
                    method, work_project, kind, routed_headers, body
                )
            else:  # pragma: no cover - route guards above are exhaustive
                response = ApiResponse.json(404, {"error": "not_found"})
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

    @classmethod
    def _project_work_route(cls, path: str) -> tuple[str, str] | None:
        prefix = "/api/v1/projects/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) != 2:
            return None
        project_id = unquote(parts[0]).strip()
        kind = parts[1]
        if not project_id or (kind != "work-hierarchy" and kind not in cls._WORK_KINDS):
            return None
        return project_id, kind

    def _project_work_response(
        self,
        method: str,
        project_id: str,
        kind: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        service = getattr(self, "_project_management", None)
        if service is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        project = self._project_for_organization(identity.organization_id, project_id)
        if project is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        action = "view" if method == "GET" and kind == "work-hierarchy" else "edit"
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "project",
                project_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        if method == "GET" and kind == "work-hierarchy":
            return self._project_hierarchy(service, identity.organization_id, project_id)
        if method != "POST" or kind not in self._WORK_KINDS:
            return ApiResponse.json(405, {"error": "method_not_allowed"})
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            record = json.loads(body)
            if not isinstance(record, dict):
                raise ValueError("request must be an object")
            child_id = self._create_project_child(
                service,
                kind,
                project_id,
                identity.organization_id,
                identity.identity_id,
                record,
            )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        return ApiResponse.json(
            201,
            {"id": child_id, "project_id": project_id, "kind": kind[:-1]},
        )

    @staticmethod
    def _project_hierarchy(service, organization_id: str, project_id: str) -> ApiResponse:
        def scoped(items):
            return [dict(item) for item in items if str(item.get("project_id", "")) == project_id]

        try:
            phases = scoped(service.phases(organization_id))
            tasks = scoped(service.tasks(organization_id))
            sprints = scoped(service.sprints(organization_id))
            allocations = scoped(service.allocations(organization_id))
        except (AttributeError, TypeError):
            return ApiResponse.json(501, {"error": "project_work_unavailable"})
        return ApiResponse.json(
            200,
            {
                "project_id": project_id,
                "phases": phases,
                "tasks": tasks,
                "sprints": sprints,
                "allocations": allocations,
            },
        )

    @staticmethod
    def _create_project_child(
        service,
        kind: str,
        project_id: str,
        organization_id: str,
        actor_id: str,
        record: dict,
    ) -> str:
        if kind == "phases":
            return service.create_phase(
                project_id,
                str(record.get("name", "")),
                organization_id=organization_id,
                actor_id=actor_id,
                description=str(record.get("description", "")),
                planned_budget=float(record.get("planned_budget", 0) or 0),
                realized_budget=float(record.get("realized_budget", 0) or 0),
            )
        if kind == "tasks":
            return service.create_task(
                project_id,
                str(record.get("title", record.get("name", ""))),
                organization_id=organization_id,
                actor_id=actor_id,
                parent_task_id=str(record.get("parent_task_id", "")).strip() or None,
                phase_id=str(record.get("phase_id", "")).strip() or None,
                sprint_id=str(record.get("sprint_id", "")).strip() or None,
                owner_id=str(record.get("owner_id", "")),
                description=str(record.get("description", "")),
                priority=str(record.get("priority", "normal")),
                start_date=str(record.get("start_date", "")),
                due_date=str(record.get("due_date", "")),
                estimate_hours=float(record.get("estimate_hours", 0) or 0),
                realized_hours=float(record.get("realized_hours", 0) or 0),
            )
        if kind == "sprints":
            return service.create_sprint(
                project_id,
                str(record.get("name", "")),
                organization_id=organization_id,
                actor_id=actor_id,
                start_date=str(record.get("start_date", "")),
                end_date=str(record.get("end_date", "")),
                status=str(record.get("status", "planned")),
                goal=str(record.get("goal", "")),
            )
        if kind == "allocations":
            return service.create_allocation(
                project_id,
                str(record.get("user_id", "")),
                organization_id=organization_id,
                actor_id=actor_id,
                start_date=str(record.get("start_date", "")),
                end_date=str(record.get("end_date", "")),
                hours_per_week=float(record.get("hours_per_week", 0) or 0),
                allocation_percent=float(record.get("allocation_percent", 0) or 0),
                role=str(record.get("role", "")),
                phase_id=str(record.get("phase_id", "")).strip() or None,
            )
        raise ValueError("unsupported project work kind")

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
