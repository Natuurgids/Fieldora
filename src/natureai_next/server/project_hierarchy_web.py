"""Managed Project hierarchy APIs and contextual browser actions.

WEB-032 keeps hierarchy semantics in the shared Project Management service. This
mixin is a transport/UI layer only: managed deployments never persist phases, tasks,
sprints or allocations through the generic science-record fallback.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie

_CHILD_ROUTES = {
    "/api/v1/phases": ("phase", "phases", "create_phase"),
    "/api/v1/tasks": ("task", "tasks", "create_task"),
    "/api/v1/sprints": ("sprint", "sprints", "create_sprint"),
    "/api/v1/allocations": ("allocation", "allocations", "create_allocation"),
}

_PROJECT_HIERARCHY_PATCH = bytes(
    r"""

/* WEB-032: contextual Project hierarchy creation backed by managed Project APIs. */
(()=>{
 if(window.__fieldoraProjectHierarchyWired)return;
 const q=id=>document.getElementById(id);
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function mount(){
  if(window.__fieldoraProjectHierarchyWired)return true;
  const cockpit=q("project-desktop-cockpit");if(!cockpit)return false;
  const toolbar=cockpit.querySelector(".cockpit-center .cockpit-toolbar");if(!toolbar)return false;
  window.__fieldoraProjectHierarchyWired=true;
  let selectedWork={kind:"project",id:""};
  const actions=document.createElement("div");actions.id="project-hierarchy-actions";actions.className="actions";actions.dataset.fieldoraAuthorizationHidden="true";
  actions.innerHTML='<button type="button" data-project-child="phase">New phase</button><button type="button" data-project-child="task">New task</button><button type="button" data-project-child="subtask" hidden>New subtask</button><button type="button" data-project-child="sprint">New sprint</button><button type="button" data-project-child="allocation">New allocation</button>';
  toolbar.prepend(actions);
  const editor=document.createElement("section");editor.id="project-hierarchy-editor";editor.className="card section";editor.hidden=true;cockpit.before(editor);
  function projectId(){return selectedProject||""}
  function labelFor(kind){return ({phase:"phase",task:"task",subtask:"subtask",sprint:"sprint",allocation:"allocation"})[kind]||kind}
  function relationshipNote(kind){
   if(kind==="subtask")return `Parent task: ${selectedWork.id}`;
   if(kind==="task"&&selectedWork.kind==="phase")return `Phase: ${selectedWork.id}`;
   if(kind==="allocation"&&selectedWork.kind==="phase")return `Phase: ${selectedWork.id}`;
   return "Selected project";
  }
  function openEditor(kind){
   const pid=projectId();if(!pid)return;
   if(kind==="subtask"&&selectedWork.kind!=="task")return;
   const common=`<p class="muted">${esc(relationshipNote(kind))}</p>`;
   let fields="";
   if(kind==="phase")fields='<label>Name<input id="project-child-name" autocomplete="off"></label><label>Description<textarea id="project-child-description"></textarea></label>';
   if(kind==="task"||kind==="subtask")fields='<label>Title<input id="project-child-title" autocomplete="off"></label><label>Description<textarea id="project-child-description"></textarea></label><label>Owner<input id="project-child-owner" autocomplete="off"></label><label>Due date<input id="project-child-due" type="date"></label>';
   if(kind==="sprint")fields='<label>Name<input id="project-child-name" autocomplete="off"></label><label>Start date<input id="project-child-start" type="date"></label><label>End date<input id="project-child-end" type="date"></label><label>Goal<textarea id="project-child-goal"></textarea></label>';
   if(kind==="allocation")fields='<label>User<input id="project-child-user" autocomplete="off"></label><label>Start date<input id="project-child-start" type="date"></label><label>End date<input id="project-child-end" type="date"></label><label>Hours / week<input id="project-child-hours" type="number" min="0" step="0.25" value="0"></label><label>Allocation %<input id="project-child-percent" type="number" min="0" step="1" value="0"></label><label>Role<input id="project-child-role" autocomplete="off"></label>';
   editor.dataset.kind=kind;editor.innerHTML=`<h2>New ${esc(labelFor(kind))}</h2>${common}<div class="form-grid">${fields}</div><div class="actions section"><button id="project-child-save" class="primary" type="button">Create ${esc(labelFor(kind))}</button><button id="project-child-cancel" type="button">Cancel</button></div><p id="project-child-message" class="status"></p>`;editor.hidden=false;
   q("project-child-cancel").onclick=()=>{editor.hidden=true};q("project-child-save").onclick=saveChild;
   editor.querySelector("input")?.focus();
  }
  async function saveChild(){
   const kind=editor.dataset.kind,pid=projectId(),message=q("project-child-message");
   const fail=text=>{message.textContent=text;message.classList.add("error")};
   let path="",record={project_id:pid};
   if(kind==="phase"){
    record.name=q("project-child-name").value.trim();record.description=q("project-child-description").value.trim();path="/api/v1/phases";if(!record.name)return fail("Phase name is required.");
   }else if(kind==="task"||kind==="subtask"){
    record.title=q("project-child-title").value.trim();record.description=q("project-child-description").value.trim();record.owner_id=q("project-child-owner").value.trim();record.due_date=q("project-child-due").value;path="/api/v1/tasks";if(!record.title)return fail("Task title is required.");
    if(kind==="subtask")record.parent_task_id=selectedWork.id;else if(selectedWork.kind==="phase")record.phase_id=selectedWork.id;
   }else if(kind==="sprint"){
    record.name=q("project-child-name").value.trim();record.start_date=q("project-child-start").value;record.end_date=q("project-child-end").value;record.goal=q("project-child-goal").value.trim();path="/api/v1/sprints";if(!record.name)return fail("Sprint name is required.");
   }else if(kind==="allocation"){
    record.user_id=q("project-child-user").value.trim();record.start_date=q("project-child-start").value;record.end_date=q("project-child-end").value;record.hours_per_week=Number(q("project-child-hours").value||0);record.allocation_percent=Number(q("project-child-percent").value||0);record.role=q("project-child-role").value.trim();if(selectedWork.kind==="phase")record.phase_id=selectedWork.id;path="/api/v1/allocations";if(!record.user_id||!record.start_date)return fail("User and start date are required.");
   }
   try{await api(path,{method:"POST",purpose:"research",body:JSON.stringify(record)});editor.hidden=true;await loadPortfolio()}catch(error){fail(error.message)}
  }
  async function authority(){
   actions.dataset.fieldoraAuthorizationHidden="true";const pid=projectId();if(!pid)return;
   try{const caps=await api(`/api/v1/projects/${encodeURIComponent(pid)}/capabilities`,{purpose:"research"});actions.dataset.fieldoraAuthorizationHidden=caps?.actions?.edit===true?"false":"true"}catch(_e){actions.dataset.fieldoraAuthorizationHidden="true"}
  }
  actions.querySelectorAll("[data-project-child]").forEach(button=>button.onclick=()=>openEditor(button.dataset.projectChild));
  document.addEventListener("click",event=>{
   const row=event.target.closest?.("[data-portfolio-id]");
   if(row){selectedWork={kind:row.dataset.kind||"",id:row.dataset.portfolioId||""};const sub=actions.querySelector('[data-project-child="subtask"]');if(sub)sub.hidden=selectedWork.kind!=="task";return}
   const project=event.target.closest?.("[data-project-tree]");if(project){selectedWork={kind:"project",id:project.dataset.projectTree||""};const sub=actions.querySelector('[data-project-child="subtask"]');if(sub)sub.hidden=true;setTimeout(authority,0)}
  },true);
  const tree=q("project-cockpit-tree");if(tree)new MutationObserver(()=>setTimeout(authority,0)).observe(tree,{childList:true,subtree:true});
  authority();return true;
 }
 if(!mount()){
  const observer=new MutationObserver(()=>{if(mount())observer.disconnect()});
  observer.observe(document.documentElement,{childList:true,subtree:true});
 }
})();
""",
    "utf-8",
)


class ProjectHierarchyWebApiMixin:
    """Route managed Project children through the authoritative shared service."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        service = getattr(self, "_project_management", None)
        child = _CHILD_ROUTES.get(route.path)
        if child is not None and service is not None and all(
            hasattr(service, name) for name in child[1:]
        ):
            routed_headers = dict(headers)
            cookie_token = _session_cookie(routed_headers.get("cookie", ""))
            if not routed_headers.get("authorization") and cookie_token:
                routed_headers["authorization"] = f"Bearer {cookie_token}"
            if method == "GET":
                response = self._managed_children(route.query, routed_headers, child)
            elif method == "POST":
                response = self._create_managed_child(routed_headers, body, child)
            else:
                response = super().dispatch(method, target, headers, body)
            browser_session = getattr(self, "_browser_session_response", None)
            if callable(browser_session) and method in {"GET", "POST"}:
                response = browser_session(
                    method, route.path, routed_headers, cookie_token, response
                )
        else:
            response = super().dispatch(method, target, headers, body)
        return self._patch_project_hierarchy_response(target, response)

    def _managed_children(
        self,
        query_string: str,
        headers: dict[str, str],
        child: tuple[str, str, str],
    ) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        resource_type, list_name, _create_name = child
        project_filter = parse_qs(query_string).get("project_id", [""])[0].strip()
        items: list[dict[str, object]] = []
        for raw in getattr(self._project_management, list_name)(identity.organization_id):
            item = dict(raw)
            project_id = str(item.get("project_id", ""))
            if project_filter and project_id != project_filter:
                continue
            resource_id = str(item.get("id", ""))
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    resource_type,
                    resource_id,
                    identity.organization_id,
                    project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if decision.allowed:
                items.append(item)
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _create_managed_child(
        self,
        headers: dict[str, str],
        body: bytes,
        child: tuple[str, str, str],
    ) -> ApiResponse:
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
            project_id = str(record["project_id"]).strip()
            if not project_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        if self._project_for_organization(identity.organization_id, project_id) is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        resource_type, list_name, _create_name = child
        project_decision = self._decisions.decide(
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
        child_decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                resource_type,
                "",
                identity.organization_id,
                project_id,
                purpose,
            )
        )
        if not project_decision.allowed or not child_decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        try:
            if resource_type == "phase":
                created_id = self._project_management.create_phase(
                    project_id,
                    str(record.get("name", "")),
                    organization_id=identity.organization_id,
                    actor_id=identity.identity_id,
                    description=str(record.get("description", "")),
                    planned_budget=float(record.get("planned_budget", 0) or 0),
                    realized_budget=float(record.get("realized_budget", 0) or 0),
                )
            elif resource_type == "task":
                created_id = self._project_management.create_task(
                    project_id,
                    str(record.get("title") or record.get("name") or ""),
                    organization_id=identity.organization_id,
                    actor_id=identity.identity_id,
                    parent_task_id=(str(record["parent_task_id"]).strip() if record.get("parent_task_id") else None),
                    phase_id=(str(record["phase_id"]).strip() if record.get("phase_id") else None),
                    sprint_id=(str(record["sprint_id"]).strip() if record.get("sprint_id") else None),
                    owner_id=str(record.get("owner_id") or record.get("assignee_id") or ""),
                    description=str(record.get("description", "")),
                    priority=str(record.get("priority", "normal")),
                    start_date=str(record.get("start_date", "")),
                    due_date=str(record.get("due_date", "")),
                    estimate_hours=float(record.get("estimate_hours") or record.get("manual_estimate") or 0),
                    realized_hours=float(record.get("realized_hours") or record.get("realized") or 0),
                )
            elif resource_type == "sprint":
                created_id = self._project_management.create_sprint(
                    project_id,
                    str(record.get("name", "")),
                    organization_id=identity.organization_id,
                    actor_id=identity.identity_id,
                    start_date=str(record.get("start_date", "")),
                    end_date=str(record.get("end_date", "")),
                    status=str(record.get("status", "planned")),
                    goal=str(record.get("goal", "")),
                )
            else:
                created_id = self._project_management.create_allocation(
                    project_id,
                    str(record.get("user_id", "")),
                    organization_id=identity.organization_id,
                    actor_id=identity.identity_id,
                    start_date=str(record.get("start_date", "")),
                    end_date=str(record.get("end_date", "")),
                    hours_per_week=float(record.get("hours_per_week", 0) or 0),
                    allocation_percent=float(record.get("allocation_percent", 0) or 0),
                    role=str(record.get("role", "")),
                    phase_id=(str(record["phase_id"]).strip() if record.get("phase_id") else None),
                )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except (TypeError, ValueError) as exc:
            return ApiResponse.json(400, {"error": "invalid_request", "detail": str(exc)})
        item = next(
            (
                dict(raw)
                for raw in getattr(self._project_management, list_name)(identity.organization_id)
                if str(raw.get("id", "")) == created_id
            ),
            None,
        )
        if item is None:
            return ApiResponse.json(500, {"error": "created_record_unavailable"})
        return ApiResponse.json(201, {"item": item})

    @staticmethod
    def _patch_project_hierarchy_response(target: str, response: ApiResponse) -> ApiResponse:
        if (
            urlsplit(target).path != "/app.js"
            or response.status != 200
            or _PROJECT_HIERARCHY_PATCH in response.body
        ):
            return response
        return ApiResponse(
            response.status,
            response.body + _PROJECT_HIERARCHY_PATCH,
            response.content_type,
            response.headers,
        )