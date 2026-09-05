from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.domain.access_control import (
    AccessDecision,
    AccessRequest,
    Identity,
    IdentityKind,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.project_runtime_web import ProjectRuntimeWebApiMixin


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = patch_managed_web_response(
        "/app.js",
        ApiResponse(
            200,
            (resource / "app.js").read_bytes(),
            "text/javascript; charset=utf-8",
        ),
    )
    (tmp_path / "app.js").write_bytes(response.body)

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


def _restricted_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    if path == "web/capabilities":
        payload = {
            "default_deny": True,
            "pages": {
                "home": True,
                "library": True,
                "observations": True,
                "projects": False,
                "research-records": False,
                "research": False,
                "dossiers": False,
                "capacity": False,
                "knowledge": True,
                "governance": False,
                "operations": False,
                "intake-review": False,
                "aiadmin": False,
                "reference": False,
                "connectors": False,
                "operator": False,
                "platform": False,
                "administration": False,
                "help": True,
            },
            "actions": {
                "projects.create": False,
                "library.import": False,
                "aiadmin.manage": False,
                "operator.manage": False,
            },
        }
    elif path == "me":
        payload = {
            "identity_id": "restricted-user",
            "display_name": "Restricted User",
            "organization_id": "local",
        }
    elif path == "help":
        payload = {
            "items": [
                {"topic_id": "quick-start", "title": "Quick start", "workspace": "home"},
                {"topic_id": "accessibility", "title": "Keyboard and accessibility", "workspace": "help"},
            ]
        }
    elif path.startswith("help/"):
        payload = {
            "topic_id": "quick-start",
            "title": "Quick start",
            "workspace": "home",
            "content": "Safe help content.",
        }
    elif path in {"health/live", "health/ready"}:
        payload = {"live": True, "ready": True}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_unauthorized_workspaces_and_actions_are_absent_and_deep_links_fail_closed(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        api_paths: list[str] = []
        page.on(
            "request",
            lambda request: api_paths.append(
                request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
            )
            if "/api/v1/" in request.url
            else None,
        )
        page.route("**/api/v1/**", _restricted_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','restricted-certification-token')"
        )
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
        page.wait_for_selector("#workspace:not([hidden])")

        assert page.locator('.nav[data-page="library"]').is_visible()
        assert page.locator('.nav[data-page="projects"]').is_hidden()
        assert page.locator('.nav[data-page="administration"]').is_hidden()
        operator_tabs = page.locator('[data-workspace-target="operator"]')
        assert operator_tabs.count() > 0
        assert all(operator_tabs.nth(index).is_hidden() for index in range(operator_tabs.count()))
        assert page.locator(".go-import").first.is_hidden()
        assert page.locator("#portfolio-new-project").is_hidden()

        assert page.locator("#home-metrics").is_hidden()
        assert page.locator("#home-projects").locator("..").is_hidden()
        assert page.locator("#home-runtime").locator("..").is_hidden()
        home_text = page.locator("#page-home").inner_text()
        assert "Projects" not in home_text
        assert "Dossiers" not in home_text
        assert "Server mode" not in home_text
        assert "Version" not in home_text
        assert "projects" not in api_paths
        assert "dossiers" not in api_paths
        assert "runtime" not in api_paths

        page.evaluate("location.hash='#projects'")
        page.wait_for_function("location.hash !== '#projects'")
        assert page.locator("#page-projects").is_hidden()
        assert page.locator("#page-home").is_visible()
        assert "projects" not in api_paths

        page.evaluate("location.hash='#operator'")
        page.wait_for_function("location.hash !== '#operator'")
        assert page.locator("#page-operator").is_hidden()
        assert page.locator("#page-home").is_visible()
        assert "operator/overview" not in api_paths

        page.locator('.nav[data-page="help"]').click()
        page.wait_for_selector("#page-help:not([hidden])")
        help_text = page.locator("#page-help").inner_text()
        assert "Administration" not in help_text
        assert "Operator" not in help_text

        browser.close()


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web059_project_runtime_controls_are_absent_and_denied_navigation_fetches_nothing(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        api_paths: list[str] = []
        page.on(
            "request",
            lambda request: api_paths.append(
                request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
            )
            if "/api/v1/" in request.url
            else None,
        )
        page.route("**/api/v1/**", _restricted_api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','restricted-certification-token')"
        )
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
        page.wait_for_selector("#workspace:not([hidden])")

        assert page.locator("#portfolio-project-work").is_hidden()
        assert page.locator("#portfolio-project-task-add").is_hidden()
        assert page.locator("#portfolio-project-evidence-link").is_hidden()

        before = tuple(api_paths)
        page.evaluate("location.hash='#projects'")
        page.wait_for_function("location.hash !== '#projects'")
        assert page.locator("#page-projects").is_hidden()
        assert page.locator("#page-home").is_visible()
        assert tuple(api_paths) == before
        assert not any(
            path == "projects"
            or path.startswith("projects/")
            or path == "tasks"
            for path in api_paths
        )
        browser.close()


class _DeniedDecisions:
    def __init__(self) -> None:
        self.requests: list[AccessRequest] = []

    def decide(self, request: AccessRequest) -> AccessDecision:
        self.requests.append(request)
        return AccessDecision(False, "denied")


class _DeniedProjectRuntimeApi(ProjectRuntimeWebApiMixin):
    def __init__(self) -> None:
        self._decisions = _DeniedDecisions()
        self._media = SimpleNamespace()

    @staticmethod
    def _identity(_headers: dict[str, str]):
        return "token", Identity(
            "restricted-user",
            IdentityKind.USER,
            "Restricted User",
            "local",
        )

    @staticmethod
    def _project_for_organization(organization_id: str, project_id: str):
        assert organization_id == "local"
        return SimpleNamespace(project_id=project_id)


def test_web059_existing_media_link_api_is_independently_denied() -> None:
    api = _DeniedProjectRuntimeApi()
    response = api.dispatch(
        "POST",
        "/api/v1/projects/project-secret/media-links",
        {"authorization": "Bearer token", "x-fieldora-purpose": "research"},
        json.dumps({"media_id": "media-secret"}).encode("utf-8"),
    )

    assert response.status == 403
    assert json.loads(response.body) == {"error": "forbidden"}
    assert len(api._decisions.requests) == 1
    request = api._decisions.requests[0]
    assert request.action == "edit"
    assert request.resource_type == "project"
    assert request.resource_id == "project-secret"
    assert request.project_id == "project-secret"
