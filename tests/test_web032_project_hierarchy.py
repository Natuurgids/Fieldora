from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_hierarchy_web import ProjectHierarchyWebApiMixin


class _Decisions:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed)


class _ProjectManagement:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, object]]] = []
        self._items = {"phases": [], "tasks": [], "sprints": [], "allocations": []}

    def phases(self, _organization_id: str):
        return tuple(self._items["phases"])

    def tasks(self, _organization_id: str):
        return tuple(self._items["tasks"])

    def sprints(self, _organization_id: str):
        return tuple(self._items["sprints"])

    def allocations(self, _organization_id: str):
        return tuple(self._items["allocations"])

    def create_phase(self, project_id: str, name: str, **kwargs):
        item = {"id": "phase-1", "project_id": project_id, "name": name}
        self._items["phases"].append(item)
        self.created.append(("phase", {"project_id": project_id, "name": name, **kwargs}))
        return "phase-1"

    def create_task(self, project_id: str, title: str, **kwargs):
        item_id = f"task-{len(self._items['tasks']) + 1}"
        item = {
            "id": item_id,
            "project_id": project_id,
            "title": title,
            "name": title,
            "parent_task_id": kwargs.get("parent_task_id") or "",
            "phase_id": kwargs.get("phase_id") or "",
            "sprint_id": kwargs.get("sprint_id") or "",
        }
        self._items["tasks"].append(item)
        self.created.append(("task", {"project_id": project_id, "title": title, **kwargs}))
        return item_id

    def create_sprint(self, project_id: str, name: str, **kwargs):
        item = {"id": "sprint-1", "project_id": project_id, "name": name}
        self._items["sprints"].append(item)
        self.created.append(("sprint", {"project_id": project_id, "name": name, **kwargs}))
        return "sprint-1"

    def create_allocation(self, project_id: str, user_id: str, **kwargs):
        item = {"id": "allocation-1", "project_id": project_id, "user_id": user_id}
        self._items["allocations"].append(item)
        self.created.append(("allocation", {"project_id": project_id, "user_id": user_id, **kwargs}))
        return "allocation-1"


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        if target == "/app.js":
            return ApiResponse(200, b"window.base=true;", "text/javascript")
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(ProjectHierarchyWebApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True) -> None:
        self._project_management = _ProjectManagement()
        self._decisions = _Decisions(allowed)

    def _identity(self, _headers):
        return "token", SimpleNamespace(identity_id="user-1", organization_id="org-1")

    def _project_for_organization(self, organization_id: str, project_id: str):
        if organization_id == "org-1" and project_id == "project-1":
            return SimpleNamespace(project_id=project_id)
        return None


def _post(api: _Api, path: str, record: dict[str, object]):
    return api.dispatch(
        "POST",
        path,
        {"authorization": "Bearer test", "x-fieldora-purpose": "research"},
        json.dumps(record).encode(),
    )


def test_web032_managed_child_routes_preserve_hierarchy_relationships() -> None:
    api = _Api()
    assert _post(api, "/api/v1/phases", {"project_id": "project-1", "name": "Survey"}).status == 201
    assert _post(
        api,
        "/api/v1/tasks",
        {"project_id": "project-1", "title": "Transect", "phase_id": "phase-1"},
    ).status == 201
    assert _post(
        api,
        "/api/v1/tasks",
        {"project_id": "project-1", "title": "Photograph", "parent_task_id": "task-1"},
    ).status == 201
    assert _post(
        api,
        "/api/v1/sprints",
        {"project_id": "project-1", "name": "Spring round", "status": "planned"},
    ).status == 201
    assert _post(
        api,
        "/api/v1/allocations",
        {
            "project_id": "project-1",
            "user_id": "researcher-1",
            "start_date": "2026-09-01",
            "phase_id": "phase-1",
        },
    ).status == 201

    tasks = api._project_management.tasks("org-1")
    assert tasks[0]["phase_id"] == "phase-1"
    assert tasks[1]["parent_task_id"] == "task-1"
    allocation = api._project_management.allocations("org-1")[0]
    assert allocation["project_id"] == "project-1"
    created_allocation = api._project_management.created[-1][1]
    assert created_allocation["phase_id"] == "phase-1"


def test_web032_direct_child_mutation_is_independently_denied() -> None:
    api = _Api(allowed=False)
    response = _post(
        api,
        "/api/v1/tasks",
        {"project_id": "project-1", "title": "Must not be created"},
    )
    assert response.status == 403
    assert json.loads(response.body) == {"error": "forbidden"}
    assert api._project_management.tasks("org-1") == ()
    assert [(r.action, r.resource_type, r.project_id) for r in api._decisions.requests] == [
        ("edit", "project", "project-1"),
        ("edit", "task", "project-1"),
    ]


@contextlib.contextmanager
def _browser_fixture(tmp_path: Path):
    html = """<!doctype html><html><body>
    <section id="project-desktop-cockpit">
      <section class="cockpit-center"><div class="cockpit-toolbar"></div></section>
      <div id="project-cockpit-tree"><button data-project-tree="project-1">Project</button></div>
    </section>
    <button id="phase-row" data-portfolio-id="phase-1" data-kind="phase">Survey</button>
    <button id="task-row" data-portfolio-id="task-1" data-kind="task">Transect</button>
    <script>
      let selectedProject="project-1"; window.calls=[]; window.portfolioReloads=0;
      async function api(path,options={}) {
        if(path.includes("/capabilities")) return {actions:{edit:true}};
        if(String(options.method||"GET").toUpperCase()==="POST") {
          window.calls.push({path,record:JSON.parse(options.body||"{}")}); return {item:{}};
        }
        return {items:[]};
      }
      async function loadPortfolio(){window.portfolioReloads++}
    </script><script src="/app.js"></script>
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
    server_thread = thread
    server_thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def test_web032_contextual_browser_actions_fill_selected_relationships(tmp_path: Path) -> None:
    with _browser_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        actions = page.locator("#project-hierarchy-actions")
        page.wait_for_function(
            "document.querySelector('#project-hierarchy-actions').dataset.fieldoraAuthorizationHidden === 'false'"
        )
        assert actions.get_by_role("button", name="＋ New phase").count() == 1
        assert actions.get_by_role("button", name="＋ New task").count() == 1
        assert actions.get_by_role("button", name="＋ New sprint").count() == 1
        assert actions.get_by_role("button", name="＋ New allocation").count() == 1

        actions.get_by_role("button", name="＋ New phase").click()
        page.locator("#project-child-name").fill("Survey phase")
        page.get_by_role("button", name="Create phase").click()
        page.wait_for_function("window.calls.length === 1")
        assert page.evaluate("window.calls[0].path") == "/api/v1/phases"
        assert page.evaluate("window.calls[0].record.project_id") == "project-1"

        page.locator("#phase-row").click()
        actions.get_by_role("button", name="＋ New task").click()
        page.locator("#project-child-title").fill("Transect")
        page.get_by_role("button", name="Create task").click()
        page.wait_for_function("window.calls.length === 2")
        assert page.evaluate("window.calls[1]") == {
            "path": "/api/v1/tasks",
            "record": {
                "project_id": "project-1",
                "title": "Transect",
                "description": "",
                "owner_id": "",
                "due_date": "",
                "phase_id": "phase-1",
            },
        }

        page.locator("#task-row").click()
        actions.get_by_role("button", name="＋ New subtask").click()
        page.locator("#project-child-title").fill("Photograph")
        page.get_by_role("button", name="Create subtask").click()
        page.wait_for_function("window.calls.length === 3")
        assert page.evaluate("window.calls[2].record.parent_task_id") == "task-1"

        actions.get_by_role("button", name="＋ New sprint").click()
        page.locator("#project-child-name").fill("Spring round")
        page.get_by_role("button", name="Create sprint").click()
        page.wait_for_function("window.calls.length === 4")
        assert page.evaluate("window.calls[3].path") == "/api/v1/sprints"

        page.locator("#phase-row").click()
        actions.get_by_role("button", name="＋ New allocation").click()
        page.locator("#project-child-user").fill("researcher-1")
        page.locator("#project-child-start").fill("2026-09-01")
        page.get_by_role("button", name="Create allocation").click()
        page.wait_for_function("window.calls.length === 5")
        assert page.evaluate("window.calls[4].record.phase_id") == "phase-1"
        assert page.evaluate("window.portfolioReloads") == 5
        browser.close()
