"""Projects/Core task editing with server-enforced authorization."""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.application.project_management import PRIORITIES, RECURRENCES
from natureai_next.application.project_task_detail import ProjectTaskDetailQuery
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie


def _validate_date(value: object, label: str) -> str:
    text = str(value or "").strip()
    if text:
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{label} must use YYYY-MM-DD") from exc
    return text


_PROJECT_TASK_EDIT_PATCH = bytes(
    r'''

/* WEB-PROJECT-TASK-EDIT-MODULE: desktop-parity task editing. */
(()=>{
 if(window.__fieldoraProjectTaskEditWired)return;window.__fieldoraProjectTaskEditWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",taskId:"",canEdit:false};
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function emitError(error,fallback){document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(error?.message||fallback)}}))}
 function ensureSurface(){const cockpit=q("project-desktop-cockpit");if(!cockpit)return false;let host=q("project-core-task-editor");if(!host){host=document.createElement("section");host.id="project-core-task-editor";host.className="card section";host.hidden=true;cockpit.before(host)}return true}
 async function authority(){state.canEdit=false;if(!state.projectId)return;try{const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});state.canEdit=caps?.actions?.edit===true}catch(error){emitError(error,"Project permissions could not be loaded.")}}
 function fail(text){const node=q("project-core-task-edit-message");if(node){node.textContent=text;node.classList.add("error")}return false}
 async function open(taskId){
  if(!state.projectId||!taskId||!state.canEdit)return;state.taskId=taskId;const pid=encodeURIComponent(state.projectId),tid=encodeURIComponent(taskId);
  try{
   const [detail,statuses,phases,sprints]=await Promise.all([api(`/api/v1/tasks/${tid}?project_id=${pid}`,{purpose:"research"}),api(`/api/v1/project-statuses?project_id=${pid}`,{purpose:"research"}),api(`/api/v1/phases?project_id=${pid}`,{purpose:"research"}),api(`/api/v1/sprints?project_id=${pid}`,{purpose:"research"})]);
   const task=detail.item;if(!task)throw new Error("Task is no longer available.");
   const options=(items,idKey,labelKey,selected,empty)=>`${empty||""}`+(items||[]).map(item=>`<option value="${esc(item[idKey]||item.id)}" ${String(item[idKey]||item.id)===String(selected||"")?"selected":""}>${esc(item[labelKey]||item.name)}</option>`).join("");
   const host=q("project-core-task-editor");host.hidden=false;host.innerHTML=`<div class="top"><div><h2>Edit task</h2><p class="muted">Task planning fields from the desktop workflow. The server independently authorizes every save.</p></div><button id="project-core-task-edit-close" type="button">Close</button></div><div class="form-grid"><label>Title<input id="project-core-task-edit-title" value="${esc(task.title||"")}"></label><label>Owner<input id="project-core-task-edit-owner" value="${esc(task.owner_id||"")}"></label><label>Status<select id="project-core-task-edit-status">${options(statuses.items,"status_id","name",task.status_id)}</select></label><label>Priority<select id="project-core-task-edit-priority">${["critical","high","normal","low"].map(v=>`<option ${v===task.priority?"selected":""}>${v}</option>`).join("")}</select></label><label>Start<input id="project-core-task-edit-start" type="date" value="${esc(task.start_date||"")}"></label><label>Strict deadline<input id="project-core-task-edit-due" type="date" value="${esc(task.due_date||"")}"></label><label>Manual estimate (h)<input id="project-core-task-edit-estimate" type="number" min="0" step="0.25" value="${Number(task.estimate_hours??0)}"></label><label>Realized (h)<input id="project-core-task-edit-realized" type="number" min="0" step="0.25" value="${Number(task.realized_hours??0)}"></label><label>Progress %<input id="project-core-task-edit-progress" type="number" min="0" max="100" step="1" value="${Number(task.progress||0)}"></label><label>Budget<input id="project-core-task-edit-budget" type="number" min="0" step="0.01" value="${Number(task.budget||0)}"></label><label>Phase<select id="project-core-task-edit-phase">${options(phases.items,"phase_id","name",task.phase_id,'<option value="">No phase</option>')}</select></label><label>Sprint<select id="project-core-task-edit-sprint">${options(sprints.items,"sprint_id","name",task.sprint_id,'<option value="">No sprint</option>')}</select></label><label>Recurrence<select id="project-core-task-edit-recurrence">${["none","daily","weekly","monthly"].map(v=>`<option ${v===(task.recurrence||"none")?"selected":""}>${v}</option>`).join("")}</select></label><label>Recurrence ends<input id="project-core-task-edit-recurrence-end" type="date" value="${esc(task.recurrence_end||"")}"></label><label><input id="project-core-task-edit-milestone" type="checkbox" ${task.milestone?"checked":""}> Milestone</label><label class="span-2">Description<textarea id="project-core-task-edit-description">${esc(task.description||"")}</textarea></label></div><div class="actions section"><button id="project-core-task-edit-save" class="primary" type="button">Save task</button></div><p id="project-core-task-edit-message" class="status"></p>`;
   q("project-core-task-edit-close").onclick=()=>{host.hidden=true};q("project-core-task-edit-save").onclick=save;
  }catch(error){emitError(error,"Task editor could not be loaded.")}
 }
 async function save(){
  if(!state.taskId||!state.projectId||!state.canEdit)return;const start=q("project-core-task-edit-start").value,due=q("project-core-task-edit-due").value,recEnd=q("project-core-task-edit-recurrence-end").value;
  if(!q("project-core-task-edit-title").value.trim())return fail("Task title is required.");if(start&&due&&due<start)return fail("Due date cannot be before start date.");
  const estimate=Number(q("project-core-task-edit-estimate").value),realized=Number(q("project-core-task-edit-realized").value),progress=Number(q("project-core-task-edit-progress").value),budget=Number(q("project-core-task-edit-budget").value);
  if([estimate,realized,budget].some(v=>!Number.isFinite(v)||v<0))return fail("Hours and budget must be zero or greater.");if(!Number.isInteger(progress)||progress<0||progress>100)return fail("Progress must be a whole number from 0 to 100.");
  const record={project_id:state.projectId,title:q("project-core-task-edit-title").value.trim(),description:q("project-core-task-edit-description").value.trim(),owner_id:q("project-core-task-edit-owner").value.trim(),status_id:q("project-core-task-edit-status").value,priority:q("project-core-task-edit-priority").value,start_date:start,due_date:due,estimate_hours:estimate,realized_hours:realized,progress,budget,phase_id:q("project-core-task-edit-phase").value||null,sprint_id:q("project-core-task-edit-sprint").value||null,recurrence:q("project-core-task-edit-recurrence").value,recurrence_end:recEnd,milestone:q("project-core-task-edit-milestone").checked};
  try{const result=await api(`/api/v1/tasks/${encodeURIComponent(state.taskId)}`,{method:"PATCH",purpose:"research",body:JSON.stringify(record)});q("project-core-task-editor").hidden=true;document.dispatchEvent(new CustomEvent("fieldora:project-work-changed",{detail:{module_id:moduleId,project_id:state.projectId,kind:"task",item:result.item}}))}catch(error){fail(error?.message||"Task could not be saved.");emitError(error,"Task could not be saved.")}
 }
 function mount(){if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();const signal=state.controller.signal;state.projectId=window.FieldoraProjects?.currentProject?.()||"";authority();q("project-desktop-cockpit")?.addEventListener("dblclick",event=>{const row=event.target.closest?.('[data-project-work-kind="task"]');if(row)open(row.dataset.projectWorkId)},{signal});document.addEventListener("fieldora:project-task-edit-request",event=>open(event.detail?.task_id||""),{signal})}
 function unmount(){state.controller?.abort();state.controller=null;state.mounted=false;const host=q("project-core-task-editor");if(host)host.hidden=true}
 document.addEventListener("fieldora:project-context-changed",event=>{state.projectId=event.detail?.project_id||"";authority()});document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraProjectTaskEdit=Object.freeze({mount,unmount,open,refreshAuthority:authority});if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
''',
    "utf-8",
)


class ProjectTaskEditModuleWebApiMixin:
    """Expose governed task-detail/edit transport and the Projects/Core editor."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        service = getattr(self, "_project_management", None)
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        task_route = route.path.startswith("/api/v1/tasks/")
        if service is not None and route.path == "/api/v1/project-statuses" and method == "GET":
            response = self._project_statuses(route.query, routed_headers)
        elif service is not None and task_route and method == "GET":
            response = self._task_detail(
                route.path.rsplit("/", 1)[-1], route.query, routed_headers
            )
        elif service is not None and task_route and method == "PATCH":
            response = self._patch_task(
                route.path.rsplit("/", 1)[-1], routed_headers, body
            )
        else:
            response = super().dispatch(method, target, headers, body)
        browser_session = getattr(self, "_browser_session_response", None)
        if (
            callable(browser_session)
            and route.path.startswith("/api/v1/")
            and method in {"GET", "PATCH"}
        ):
            response = browser_session(
                method, route.path, routed_headers, cookie_token, response
            )
        return self._patch_browser(target, response)

    def _identity_or_401(self, headers: dict[str, str]):
        try:
            return self._identity(headers)[1], None
        except AuthenticationFailed:
            return None, ApiResponse.json(401, {"error": "unauthorized"})

    def _project_statuses(self, query: str, headers: dict[str, str]) -> ApiResponse:
        identity, error = self._identity_or_401(headers)
        if error is not None:
            return error
        project_id = parse_qs(query).get("project_id", [""])[0].strip()
        if (
            not project_id
            or self._project_for_organization(identity.organization_id, project_id) is None
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        items = [dict(row) for row in self._project_management.statuses(project_id)]
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _task_detail(
        self, task_id: str, query: str, headers: dict[str, str]
    ) -> ApiResponse:
        identity, error = self._identity_or_401(headers)
        if error is not None:
            return error
        project_id = parse_qs(query).get("project_id", [""])[0].strip()
        if (
            not project_id
            or self._project_for_organization(identity.organization_id, project_id) is None
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        decisions = (
            self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "project",
                    project_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            ),
            self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "task",
                    task_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            ),
        )
        if not all(decision.allowed for decision in decisions):
            return ApiResponse.json(403, {"error": "forbidden"})
        reader = ProjectTaskDetailQuery(self._project_management.database_path)
        item = reader.get(project_id, task_id)
        if item is None:
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(200, {"item": item})

    def _patch_task(
        self, task_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        identity, error = self._identity_or_401(headers)
        if error is not None:
            return error
        try:
            record = json.loads(body)
            if not isinstance(record, dict):
                raise ValueError("JSON object required")
            project_id = str(record.pop("project_id", "")).strip()
            if not project_id:
                raise ValueError("project_id is required")
        except (json.JSONDecodeError, ValueError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        if self._project_for_organization(identity.organization_id, project_id) is None:
            return ApiResponse.json(404, {"error": "not_found"})
        reader = ProjectTaskDetailQuery(self._project_management.database_path)
        if reader.get(project_id, task_id) is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        decisions = (
            self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "edit",
                    "project",
                    project_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            ),
            self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "edit",
                    "task",
                    task_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            ),
        )
        if not all(decision.allowed for decision in decisions):
            return ApiResponse.json(403, {"error": "forbidden"})
        allowed = {
            "title",
            "description",
            "status_id",
            "owner_id",
            "priority",
            "start_date",
            "due_date",
            "estimate_hours",
            "budget",
            "progress",
            "recurrence",
            "recurrence_end",
            "milestone",
            "phase_id",
            "sprint_id",
            "realized_hours",
        }
        changes = {key: value for key, value in record.items() if key in allowed}
        if not changes:
            return ApiResponse.json(
                400,
                {
                    "error": "invalid_request",
                    "detail": "no editable task fields supplied",
                },
            )
        try:
            self._validate_changes(project_id, changes)
            self._project_management.update_task(
                task_id, actor_id=identity.identity_id, **changes
            )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except (TypeError, ValueError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        item = reader.get(project_id, task_id)
        if item is None:
            return ApiResponse.json(500, {"error": "updated_record_unavailable"})
        return ApiResponse.json(200, {"item": item})

    def _validate_changes(self, project_id: str, changes: dict[str, object]) -> None:
        if "title" in changes and not str(changes["title"]).strip():
            raise ValueError("task title is required")
        if "priority" in changes and str(changes["priority"]) not in PRIORITIES:
            raise ValueError("invalid task priority")
        if "recurrence" in changes and str(changes["recurrence"]) not in RECURRENCES:
            raise ValueError("invalid task recurrence")
        start = _validate_date(changes.get("start_date", ""), "task start date")
        due = _validate_date(changes.get("due_date", ""), "task due date")
        _validate_date(changes.get("recurrence_end", ""), "recurrence end date")
        if start and due and due < start:
            raise ValueError("due date cannot be before start date")
        for field in ("estimate_hours", "realized_hours", "budget"):
            if field in changes:
                value = float(changes[field])
                if value < 0:
                    raise ValueError(f"{field} must be zero or greater")
                changes[field] = value
        if "progress" in changes:
            value = int(changes["progress"])
            if float(changes["progress"]) != value or not 0 <= value <= 100:
                raise ValueError("progress must be a whole number from 0 to 100")
            changes["progress"] = value
        if "milestone" in changes:
            changes["milestone"] = bool(changes["milestone"])
        if "status_id" in changes:
            status_ids = {
                str(item.get("status_id") or item.get("id") or "")
                for item in self._project_management.statuses(project_id)
            }
            if str(changes["status_id"] or "") not in status_ids:
                raise ValueError("status does not belong to project")
        if "phase_id" in changes and changes["phase_id"]:
            phase_ids = {
                str(item.get("phase_id") or item.get("id") or "")
                for item in self._project_management.phases(project_id)
            }
            if str(changes["phase_id"]) not in phase_ids:
                raise ValueError("phase does not belong to project")
        if "sprint_id" in changes and changes["sprint_id"]:
            sprint_ids = {
                str(item.get("sprint_id") or item.get("id") or "")
                for item in self._project_management.sprints(project_id)
            }
            if str(changes["sprint_id"]) not in sprint_ids:
                raise ValueError("sprint does not belong to project")

    @staticmethod
    def _patch_browser(target: str, response: ApiResponse) -> ApiResponse:
        if (
            urlsplit(target).path != "/app.js"
            or response.status != 200
            or _PROJECT_TASK_EDIT_PATCH in response.body
        ):
            return response
        return ApiResponse(
            response.status,
            response.body + _PROJECT_TASK_EDIT_PATCH,
            response.content_type,
            response.headers,
        )
