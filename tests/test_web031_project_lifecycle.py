from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_lifecycle_web import ProjectLifecycleWebApiMixin


class _Decisions:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed)


class _ManagedProjects:
    def __init__(self) -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            organization_id="org-1",
            name="Field survey",
            description="Initial",
            status="active",
            owner_id="user-1",
            start_date="2026-08-30",
            due_date="2026-09-30",
            budget=100.0,
            currency="EUR",
            revision=7,
        )
        self.calls: list[dict[str, object]] = []

    def projects(self, _organization_id: str):
        return (self.project,)

    def set_project_status(
        self,
        project_id: str,
        status: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> int:
        self.calls.append(
            {
                "project_id": project_id,
                "status": status,
                "organization_id": organization_id,
                "actor_id": actor_id,
                "expected_revision": expected_revision,
            }
        )
        if expected_revision != self.project.revision:
            raise ValueError("project revision conflict")
        self.project.status = status
        self.project.revision += 1
        return self.project.revision


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        if target == "/app.js":
            return ApiResponse(200, b"window.base=true;", "text/javascript")
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(ProjectLifecycleWebApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True) -> None:
        self._project_management = _ManagedProjects()
        self._decisions = _Decisions(allowed)

    def _identity(self, _headers):
        return "token", SimpleNamespace(identity_id="user-1", organization_id="org-1")

    def _project_for_organization(self, organization_id: str, project_id: str):
        if organization_id == "org-1" and project_id == "project-1":
            return self._project_management.project
        return None

    @staticmethod
    def _project_item(project):
        return {
            "id": project.project_id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "owner_id": project.owner_id,
            "start_date": project.start_date,
            "due_date": project.due_date,
            "budget": project.budget,
            "currency": project.currency,
            "revision": project.revision,
        }


def _patch_status(api: _Api, record: dict[str, object]):
    return api.dispatch(
        "PATCH",
        "/api/v1/projects/project-1/status",
        {"authorization": "Bearer test", "x-fieldora-purpose": "research"},
        json.dumps(record).encode(),
    )


def test_web031_status_uses_managed_project_service_and_revision_pbacc() -> None:
    api = _Api()
    response = _patch_status(api, {"expected_revision": 7, "status": "cancelled"})
    assert response.status == 200
    payload = json.loads(response.body)
    assert payload["item"]["status"] == "cancelled"
    assert payload["item"]["revision"] == 8
    assert api._project_management.calls == [
        {
            "project_id": "project-1",
            "status": "cancelled",
            "organization_id": "org-1",
            "actor_id": "user-1",
            "expected_revision": 7,
        }
    ]
    assert [(r.action, r.resource_type, r.project_id) for r in api._decisions.requests] == [
        ("edit", "project", "project-1")
    ]


def test_web031_status_denial_and_revision_conflict_fail_closed() -> None:
    denied = _Api(allowed=False)
    assert _patch_status(denied, {"expected_revision": 7, "status": "cancelled"}).status == 403
    assert denied._project_management.calls == []

    conflict = _Api()
    response = _patch_status(conflict, {"expected_revision": 6, "status": "archived"})
    assert response.status == 409
    payload = json.loads(response.body)
    assert payload["error"] == "revision_conflict"
    assert payload["current"]["revision"] == 7
    assert payload["current"]["status"] == "active"


@contextlib.contextmanager
def _browser_fixture(tmp_path: Path):
    html = """<!doctype html><html><body>
    <main id="page-projects">
      <div class="top"></div>
      <section id="project-desktop-cockpit">
        <section class="cockpit-center"><div class="cockpit-toolbar"></div></section>
        <div id="project-cockpit-tree"><button data-project-tree="project-1">Field survey</button></div>
      </section>
    </main>
    <script>
      let selectedProject="project-1";
      let projects=[{id:"project-1",name:"Field survey",description:"Initial",status:"active",owner_id:"user-1",start_date:"2026-08-30",due_date:"2026-09-30",budget:100,currency:"EUR",revision:7}];
      window.calls=[];window.portfolioReloads=0;window.allowEdit=true;window.forceConflict=false;
      function projectOptions(){}
      async function loadPortfolio(){window.portfolioReloads++}
      async function api(path,options={}) {
        if(path.includes("/capabilities")) return {actions:{edit:window.allowEdit}};
        if(path==="/api/v1/projects") return {items:projects};
        if(String(options.method||"GET").toUpperCase()==="PATCH") {
          const record=JSON.parse(options.body||"{}");window.calls.push({path,method:"PATCH",record});
          if(window.forceConflict){
            projects=[{...projects[0],name:"Server change",description:"Current governed value",revision:Number(record.expected_revision)+1}];
            const error=new Error("revision_conflict");error.code="revision_conflict";throw error;
          }
          let project={...projects[0],revision:Number(record.expected_revision)+1};
          if(path.endsWith("/status")) project={...project,status:record.status};
          else if(path.endsWith("/archive")) project={...project,status:"archived"};
          else project={...project,name:record.name,description:record.description,start_date:record.start_date,due_date:record.due_date,budget:record.budget,currency:record.currency};
          projects=[project];return {item:project,revision:project.revision};
        }
        return {items:[]};
      }
    </script>
    <script src="/app.js"></script>
    </body></html>"""
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    app = _Api().dispatch("GET", "/app.js", {}, b"")
    (tmp_path / "app.js").write_bytes(app.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web031_browser_edit_status_archive_advance_server_revision(tmp_path: Path) -> None:
    with _browser_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        edit = page.locator("#portfolio-edit-project")
        page.wait_for_function(
            "document.querySelector('#portfolio-edit-project').dataset.fieldoraAuthorizationHidden === 'false'"
        )
        edit.click()
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == "Server revision 7"
        page.locator("#portfolio-project-lifecycle-name").fill("Field survey revised")
        page.get_by_role("button", name="Save details").click()
        page.wait_for_function("window.calls.length === 1")
        assert page.evaluate("window.calls[0]") == {
            "path": "/api/v1/projects/project-1",
            "method": "PATCH",
            "record": {
                "expected_revision": 7,
                "name": "Field survey revised",
                "description": "Initial",
                "start_date": "2026-08-30",
                "due_date": "2026-09-30",
                "budget": 100,
                "currency": "EUR",
            },
        }
        page.locator("#portfolio-project-lifecycle-status").select_option("cancelled")
        page.get_by_role("button", name="Apply status").click()
        page.wait_for_function("window.calls.length === 2")
        assert page.evaluate("window.calls[1]") == {
            "path": "/api/v1/projects/project-1/status",
            "method": "PATCH",
            "record": {"expected_revision": 8, "status": "cancelled"},
        }
        page.get_by_role("button", name="Archive project").click()
        page.wait_for_function("window.calls.length === 3")
        assert page.evaluate("window.calls[2]") == {
            "path": "/api/v1/projects/project-1/archive",
            "method": "PATCH",
            "record": {"expected_revision": 9},
        }
        page.wait_for_function("window.portfolioReloads === 3")
        browser.close()


def test_web031_browser_conflict_reloads_latest_without_retry(tmp_path: Path) -> None:
    with _browser_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function(
            "document.querySelector('#portfolio-edit-project').dataset.fieldoraAuthorizationHidden === 'false'"
        )
        page.evaluate("window.forceConflict=true")
        page.locator("#portfolio-edit-project").click()
        page.locator("#portfolio-project-lifecycle-name").fill("My stale change")
        page.get_by_role("button", name="Save details").click()
        page.wait_for_function("window.calls.length === 1")
        page.wait_for_function(
            "document.querySelector('#portfolio-project-lifecycle-message').textContent.includes('Latest values reloaded')"
        )
        assert page.locator("#portfolio-project-lifecycle-name").input_value() == "Server change"
        assert page.locator("#portfolio-project-lifecycle-revision").inner_text() == "Server revision 8"
        assert page.evaluate("window.calls.length") == 1
        browser.close()
