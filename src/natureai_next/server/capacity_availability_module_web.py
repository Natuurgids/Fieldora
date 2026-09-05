"""Capacity availability transport and browser module with Project-scoped governance.

The Qt reference keeps schedules, absence/PTO, organisational obligations and
allocations in one Project availability view.  This adapter exposes only
Project-scoped aggregate availability to viewers; private HR detail is not sent
to the browser.  Mutations require independent Project edit authorization and a
Project member target before the shared Project Management service is called.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie

_ABSENCE_TYPES = frozenset(
    {"annual_leave", "pto", "sick_leave", "medical_appointment", "other"}
)
_CAPACITY_ALLOCATION_OWNER_MARKER = b"WEB-CAPACITY-MODULE"
_LEGACY_CAPACITY_SAVE_START = b"async function saveCapacity(){"
_LEGACY_CAPACITY_SAVE_END = b"async function loadDossierWorkspace(){"
_LEGACY_CAPACITY_SAVE_WIRING = b'q("capacity-save").onclick=saveCapacity;'


def _retire_legacy_capacity_create(body: bytes) -> bytes:
    """Retire the shared legacy editor only when allocation ownership also exists."""

    if _CAPACITY_ALLOCATION_OWNER_MARKER not in body:
        return body
    start = body.find(_LEGACY_CAPACITY_SAVE_START)
    end = body.find(_LEGACY_CAPACITY_SAVE_END, start) if start >= 0 else -1
    if start >= 0 and end >= 0:
        body = body[:start] + body[end:]
    return body.replace(_LEGACY_CAPACITY_SAVE_WIRING, b"", 1)


_CAPACITY_AVAILABILITY_PATCH = bytes(
    r'''

/* WEB-CAPACITY-AVAILABILITY-MODULE: governed Project availability parity. */
(()=>{
 if(window.__fieldoraCapacityAvailabilityWired)return;window.__fieldoraCapacityAvailabilityWired=true;
 const moduleId="capacity",q=id=>document.getElementById(id);
 const state={mounted:false,controller:null,projectId:"",rows:[],templates:[],canEdit:false,legacy:[]};
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function fail(text){const node=q("capacity-availability-message");if(node){node.textContent=text;node.classList.add("error")}return false}
 function clearMessage(){const node=q("capacity-availability-message");if(node){node.textContent="";node.classList.remove("error")}}
 function report(error,fallback){const text=error?.message||fallback;fail(text);document.dispatchEvent(new CustomEvent("fieldora:module-error",{detail:{module_id:moduleId,error:String(text)}}))}
 function hideLegacy(){const page=q("page-capacity");if(!page)return;state.legacy=[...page.children].filter(node=>node.id!=="capacity-availability-owned"&&node.id!=="capacity-project-context"&&!node.classList.contains("top"));state.legacy.forEach(node=>node.hidden=true)}
 function restoreLegacy(){state.legacy.forEach(node=>node.hidden=false);state.legacy=[]}
 function ensureSurface(){
  const page=q("page-capacity");if(!page)return false;let host=q("capacity-availability-owned");
  if(!host){host=document.createElement("section");host.id="capacity-availability-owned";host.className="card section";host.innerHTML='<div class="top"><div><h2>Availability</h2><p class="muted" id="capacity-availability-project">Open a Project to inspect team availability.</p></div><button id="capacity-availability-refresh" type="button" data-fieldora-action="capacity.availability.view">Refresh</button></div><p class="muted">Scheduled work, leave/PTO/absence, organisational obligations and Project allocations are date/time-based. Project users see availability impact; private HR details stay server-side.</p><div id="capacity-availability-list" class="list section"></div><div id="capacity-availability-actions" class="actions section" hidden><button type="button" data-capacity-availability-create="schedule" data-fieldora-action="capacity.schedule.assign">Assign schedule</button><button type="button" data-capacity-availability-create="absence" data-fieldora-action="capacity.absence.register">Register absence</button><button type="button" data-capacity-availability-create="obligation" data-fieldora-action="capacity.obligation.create">Add organisational obligation</button></div><section id="capacity-availability-editor" class="section" hidden></section><p id="capacity-availability-message" class="status" role="status"></p>';page.querySelector(".top")?.after(host)}
  return true;
 }
 function render(){
  if(!ensureSurface())return;const label=q("capacity-availability-project"),list=q("capacity-availability-list"),actions=q("capacity-availability-actions");if(label)label.textContent=state.projectId?`Project ${state.projectId}`:"Open a Project to inspect team availability.";if(actions)actions.hidden=!state.canEdit||!state.projectId;
  if(!list)return;if(!state.projectId){list.innerHTML='<div class="empty">No Project context selected.</div>';return}
  list.innerHTML=state.rows.length?state.rows.map(row=>`<div class="row" data-capacity-user="${esc(row.user_id)}"><strong>${esc(row.user_id)}</strong><span>${esc(row.role||"member")}</span><span>${esc(row.scheduled_hours??0)} h scheduled</span><span>${esc(row.absence_hours??0)} h absence · ${esc(row.organisational_hours??0)} h organisation</span><span>${esc(row.allocated_hours??0)} h allocated · ${esc(row.remaining_hours??0)} h remaining</span></div>`).join(""):'<div class="empty">No Project members are available in this view.</div>';
 }
 async function authority(){state.canEdit=false;if(!state.projectId){render();return}try{const caps=await api(`/api/v1/projects/${encodeURIComponent(state.projectId)}/capabilities`,{purpose:"research"});state.canEdit=caps?.actions?.edit===true}catch(_error){state.canEdit=false}render()}
 async function refresh(){render();if(!state.projectId)return;try{const pid=encodeURIComponent(state.projectId);const result=await api(`/api/v1/capacity/availability?project_id=${pid}`,{purpose:"research"});state.rows=result.items||[];state.templates=result.schedule_templates||[];clearMessage();render()}catch(error){state.rows=[];render();report(error,"Availability could not be loaded.")}}
 function editorFields(kind){
  const users=state.rows.map(row=>`<option value="${esc(row.user_id)}">${esc(row.user_id)}</option>`).join("");
  if(kind==="schedule"){const templates=state.templates.map(row=>`<option value="${esc(row.template_id)}">${esc(row.name)}</option>`).join("");return `<label>User<select id="capacity-editor-user">${users}</select></label><label>Schedule template<select id="capacity-editor-template">${templates}</select></label><label>Effective from<input id="capacity-editor-start" type="date"></label>`}
  if(kind==="absence")return `<label>User<select id="capacity-editor-user">${users}</select></label><label>Type<select id="capacity-editor-type"><option>annual_leave</option><option>pto</option><option>sick_leave</option><option>medical_appointment</option><option>other</option></select></label><label>Starts<input id="capacity-editor-start" type="datetime-local"></label><label>Ends<input id="capacity-editor-end" type="datetime-local"></label>`;
  return `<label>User<select id="capacity-editor-user">${users}</select></label><label>Starts<input id="capacity-editor-start" type="datetime-local"></label><label>Ends<input id="capacity-editor-end" type="datetime-local"></label><label>Meeting, seminar or obligation<input id="capacity-editor-title"></label>`;
 }
 function openEditor(kind){if(!state.canEdit||!state.projectId)return;const editor=q("capacity-availability-editor");if(!editor)return;editor.dataset.kind=kind;editor.hidden=false;editor.innerHTML=`<h3>${kind==="schedule"?"Assign work schedule":kind==="absence"?"Register absence":"Add organisational obligation"}</h3><div class="form-grid">${editorFields(kind)}</div><div class="actions section"><button id="capacity-editor-save" class="primary" type="button">Save</button><button id="capacity-editor-cancel" type="button">Cancel</button></div>`;q("capacity-editor-cancel").onclick=()=>{editor.hidden=true};q("capacity-editor-save").onclick=saveEditor}
 async function saveEditor(){
  const editor=q("capacity-availability-editor"),kind=editor?.dataset.kind,user=q("capacity-editor-user")?.value||"",start=q("capacity-editor-start")?.value||"",end=q("capacity-editor-end")?.value||"";if(!user)return fail("Project member is required.");if(!start)return fail("Start date is required.");if(end&&end<=start)return fail("End must be after start.");
  let path="",record={project_id:state.projectId,user_id:user};
  if(kind==="schedule"){const template=q("capacity-editor-template")?.value||"";if(!template)return fail("Schedule template is required.");path="/api/v1/capacity/schedules";record.template_id=template;record.effective_from=start}
  else if(kind==="absence"){path="/api/v1/capacity/absences";record.start_at=start;record.end_at=end;record.absence_type=q("capacity-editor-type")?.value||"other"}
  else{const title=q("capacity-editor-title")?.value.trim()||"";if(!title)return fail("Obligation title is required.");path="/api/v1/capacity/obligations";record.start_at=start;record.end_at=end;record.title=title;record.obligation_type="organisation"}
  try{await api(path,{method:"POST",purpose:"research",body:JSON.stringify(record)});editor.hidden=true;clearMessage();await refresh();document.dispatchEvent(new CustomEvent("fieldora:capacity-availability-changed",{detail:{module_id:moduleId,project_id:state.projectId,kind}}))}catch(error){report(error,"Availability record could not be saved.")}
 }
 async function setProject(projectId){state.projectId=String(projectId||"");await authority();await refresh()}
 function mount(){if(state.mounted)return;if(!ensureSurface())return;state.mounted=true;state.controller=new AbortController();hideLegacy();const signal=state.controller.signal;q("capacity-availability-refresh")?.addEventListener("click",refresh,{signal});q("capacity-availability-actions")?.addEventListener("click",event=>{const button=event.target.closest?.("[data-capacity-availability-create]");if(button)openEditor(button.dataset.capacityAvailabilityCreate)},{signal});state.projectId=window.FieldoraCapacity?.currentProject?.()||state.projectId;authority();refresh()}
 function unmount(){if(!state.mounted)return;state.controller?.abort();state.controller=null;state.mounted=false;restoreLegacy();q("capacity-availability-editor")?.setAttribute("hidden","")}
 document.addEventListener("fieldora:capacity-project-changed",event=>setProject(event.detail?.project_id||""));document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)mount()});document.addEventListener("fieldora:module-unmount",event=>{if(event.detail?.module?.module_id===moduleId)unmount()});
 window.FieldoraCapacityAvailability=Object.freeze({mount,unmount,refresh,setProject});if(window.FieldoraModules?.current?.()?.module_id===moduleId)mount();
})();
''',
    "utf-8",
)


class CapacityAvailabilityModuleWebApiMixin:
    """Expose Project-scoped availability reads/writes and the Capacity adapter."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        owned = route.path.startswith("/api/v1/capacity/")
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        if route.path == "/api/v1/capacity/availability" and method == "GET":
            response = self._availability(route.query, routed_headers)
        elif route.path in {
            "/api/v1/capacity/schedules",
            "/api/v1/capacity/absences",
            "/api/v1/capacity/obligations",
        } and method == "POST":
            response = self._create_availability(route.path, routed_headers, body)
        else:
            owned = False
            response = super().dispatch(method, target, headers, body)
        browser_session = getattr(self, "_browser_session_response", None)
        if owned and callable(browser_session):
            response = browser_session(method, route.path, routed_headers, cookie_token, response)
        return self._patch_browser(target, response)

    def _identity_or_401(self, headers: dict[str, str]):
        try:
            return self._identity(headers)[1], None
        except AuthenticationFailed:
            return None, ApiResponse.json(401, {"error": "unauthorized"})

    def _authorize_project(self, headers: dict[str, str], project_id: str, action: str):
        identity, error = self._identity_or_401(headers)
        if error is not None:
            return None, error
        if (
            not project_id
            or self._project_for_organization(identity.organization_id, project_id) is None
        ):
            return None, ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "project",
                project_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return None, ApiResponse.json(403, {"error": "forbidden"})
        return identity, None

    def _availability(self, query: str, headers: dict[str, str]) -> ApiResponse:
        project_id = parse_qs(query).get("project_id", [""])[0].strip()
        _identity, error = self._authorize_project(headers, project_id, "view")
        if error is not None:
            return error
        service = getattr(self, "_project_management", None)
        if service is None or not all(
            hasattr(service, name)
            for name in ("workload", "schedule_templates", "project_members")
        ):
            return ApiResponse.json(501, {"error": "capacity_backend_unavailable"})
        items = [dict(row) for row in service.workload(project_id)]
        templates = [dict(row) for row in service.schedule_templates()]
        return ApiResponse.json(
            200,
            {
                "items": items,
                "count": len(items),
                "schedule_templates": templates,
            },
        )

    def _create_availability(
        self, path: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            record = json.loads(body)
            if not isinstance(record, dict):
                raise ValueError("JSON object required")
            project_id = str(record.get("project_id", "")).strip()
            user_id = str(record.get("user_id", "")).strip()
            if not project_id or not user_id:
                raise ValueError("project_id and user_id are required")
        except (json.JSONDecodeError, ValueError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        identity, error = self._authorize_project(headers, project_id, "edit")
        if error is not None:
            return error
        service = getattr(self, "_project_management", None)
        required = {
            "/api/v1/capacity/schedules": "assign_work_schedule",
            "/api/v1/capacity/absences": "add_absence",
            "/api/v1/capacity/obligations": "add_organisational_obligation",
        }[path]
        if service is None or not all(
            hasattr(service, name) for name in (required, "project_members")
        ):
            return ApiResponse.json(501, {"error": "capacity_backend_unavailable"})
        members = {str(row.get("user_id", "")) for row in service.project_members(project_id)}
        if user_id not in members:
            return ApiResponse.json(400, {"error": "invalid_project_member"})
        try:
            if path.endswith("/schedules"):
                template_id = str(record.get("template_id", "")).strip()
                effective_from = str(record.get("effective_from", "")).strip()
                if not template_id or not effective_from:
                    raise ValueError("template_id and effective_from are required")
                templates = {
                    str(row.get("template_id", "")) for row in service.schedule_templates()
                }
                if template_id not in templates:
                    raise ValueError("unknown schedule template")
                item_id = service.assign_work_schedule(
                    user_id,
                    template_id,
                    effective_from,
                    actor_id=identity.identity_id,
                )
                kind = "schedule"
            elif path.endswith("/absences"):
                absence_type = str(record.get("absence_type", "")).strip()
                if absence_type not in _ABSENCE_TYPES:
                    raise ValueError("unsupported absence type")
                item_id = service.add_absence(
                    user_id,
                    str(record.get("start_at", "")),
                    str(record.get("end_at", "")),
                    absence_type,
                    actor_id=identity.identity_id,
                )
                kind = "absence"
            else:
                title = str(record.get("title", "")).strip()
                if not title:
                    raise ValueError("obligation title is required")
                item_id = service.add_organisational_obligation(
                    user_id,
                    str(record.get("start_at", "")),
                    str(record.get("end_at", "")),
                    str(record.get("obligation_type", "organisation")),
                    title,
                    actor_id=identity.identity_id,
                )
                kind = "obligation"
        except (KeyError, TypeError, ValueError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        return ApiResponse.json(201, {"id": item_id, "kind": kind})

    @staticmethod
    def _patch_browser(target: str, response: ApiResponse) -> ApiResponse:
        if urlsplit(target).path != "/app.js" or response.status != 200:
            return response
        body = _retire_legacy_capacity_create(response.body)
        if _CAPACITY_AVAILABILITY_PATCH not in body:
            body += _CAPACITY_AVAILABILITY_PATCH
        if body == response.body:
            return response
        return ApiResponse(response.status, body, response.content_type, response.headers)
