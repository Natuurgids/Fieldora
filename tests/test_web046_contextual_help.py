from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.help import SERVER_HELP_TOPICS, help_catalogue, help_topic
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.web_capabilities import project_help_response

ROOT = Path(__file__).parents[1]
APP = (ROOT / "src/natureai_next/resources/server_web/app.js").read_text()

EXPECTED_CONTEXT_HELP = {
    "home": "quick-start",
    "library": "library",
    "observations": "observations",
    "projects": "projects",
    "capacity": "capacity",
    "research": "research",
    "dossiers": "dossiers",
    "knowledge": "knowledge",
    "administration": "health",
    "aiadmin": "ai-platform",
    "reference": "reference-data",
    "connectors": "connectors",
    "platform": "platform",
    "operations": "operations",
    "help": "accessibility",
}
NEW_TOPICS = {
    "projects": "projects",
    "capacity": "capacity",
    "dossiers": "dossiers",
    "ai-platform": "aiadmin",
    "reference-data": "reference",
    "connectors": "connectors",
    "platform": "platform",
    "operations": "operations",
}


def test_web046_context_map_and_catalogue_are_one_to_one_and_packaged() -> None:
    topics = {topic.topic_id: topic for topic in SERVER_HELP_TOPICS}
    for page, topic_id in EXPECTED_CONTEXT_HELP.items():
        assert f'{page}:"{topic_id}"' in APP
    assert '}[page]||"quick-start"' in APP
    for topic_id, workspace in NEW_TOPICS.items():
        assert topic_id in topics
        assert topics[topic_id].workspace == workspace
        resolved = help_topic(topic_id)
        assert resolved is not None
        assert resolved["workspace"] == workspace
        assert len(resolved["content"]) > 80
        assert "This packaged guide is unavailable." not in resolved["content"]


class AccessRepository:
    def __init__(self, identity: Identity, policies: tuple[Policy, ...]) -> None:
        self.identity = identity
        self._policies = policies
        self.audit: list[dict] = []

    def identities(self):
        return (self.identity,)

    def policies(self):
        return self._policies

    def role_ids(self, _subject_id: str, _organization_id: str, _project_id: str):
        return ()

    def contract(self, _contract_id: str):
        return None

    def append_audit(self, payload: dict) -> None:
        self.audit.append(payload)


def _application(repository: AccessRepository):
    return SimpleNamespace(
        _access_repository=repository,
        _decisions=PolicyDecisionService(repository),
        _identity=lambda _headers: ("test-token", repository.identity),
    )


def test_web046_denied_workspace_topics_are_filtered_and_direct_lookup_fails_closed() -> None:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")
    allow_library = Policy(
        policy_id="allow-library",
        name="allow-library",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.DIRECT,
        source_id="allow-library",
        subject_id="user-1",
        role_id="",
        actions=("view",),
        resource_types=("asset",),
        organization_id="local",
        project_id="",
        purposes=("research",),
    )
    app = _application(AccessRepository(identity, (allow_library,)))
    projected = project_help_response(
        app,
        "/api/v1/help",
        {},
        ApiResponse.json(200, {"items": list(help_catalogue())}),
    )
    visible = {item["topic_id"] for item in json.loads(projected.body)["items"]}
    assert "library" in visible
    assert not (set(NEW_TOPICS) & visible)

    denied_topic = help_topic("projects")
    assert denied_topic is not None
    denied = project_help_response(
        app,
        "/api/v1/help/projects",
        {},
        ApiResponse.json(200, denied_topic),
    )
    assert denied.status == 404
    assert json.loads(denied.body) == {"error": "help_topic_not_found"}


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = ROOT / "src/natureai_next/resources/server_web"
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = patch_managed_web_response(
        "/app.js",
        ApiResponse(200, (resource / "app.js").read_bytes(), "text/javascript; charset=utf-8"),
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


def _mock_api(route: Route) -> None:
    path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
    if path == "web/capabilities":
        payload = {
            "default_deny": True,
            "pages": {page: True for page in (
                "home", "library", "observations", "projects", "research-records", "research",
                "dossiers", "capacity", "knowledge", "governance", "operations", "intake-review",
                "aiadmin", "reference", "connectors", "operator", "platform", "administration", "help",
            )},
            "actions": {"projects.create": True, "library.import": True, "aiadmin.manage": True, "operator.manage": True},
        }
    elif path == "me":
        payload = {"identity_id": "admin-1", "display_name": "Administrator", "organization_id": "local"}
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    elif path in {"health/live", "health/ready"}:
        payload = {"live": True, "ready": True}
    elif path == "status":
        payload = {"version": "5.4.0"}
    elif path == "audit":
        payload = {"items": [], "chain_verified": True}
    elif path == "platform/parity":
        payload = {"platforms": {}}
    elif path == "platform/features":
        payload = {"items": []}
    elif path == "help":
        payload = {"items": []}
    elif path.startswith("help/"):
        topic_id = path.split("/", 1)[1]
        payload = {"topic_id": topic_id, "title": topic_id, "workspace": "help", "content": f"Packaged {topic_id} help"}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web046_f1_opens_each_expected_context_topic_in_managed_client(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        requested_topics: list[str] = []

        def route_api(route: Route) -> None:
            path = route.request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
            if path.startswith("help/"):
                requested_topics.append(path.split("/", 1)[1])
            _mock_api(route)

        page.route("**/api/v1/**", route_api)
        page.add_init_script("sessionStorage.setItem('fieldora-session','web046-certification-token')")
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
        page.wait_for_selector("#workspace:not([hidden])")

        for page_name, topic_id in EXPECTED_CONTEXT_HELP.items():
            page.locator(f'.nav[data-page="{page_name}"]').click()
            page.keyboard.press("F1")
            page.wait_for_function(
                "expected => document.getElementById('help-title').textContent === expected",
                arg=topic_id,
            )
            assert requested_topics[-1] == topic_id

        browser.close()
