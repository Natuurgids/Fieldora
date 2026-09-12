from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.optimistic_concurrency_web import (
    _OPTIMISTIC_CONCURRENCY_PATCH,
    OptimisticConcurrencyWebApiMixin,
)

_BASE_SCRIPT = b"""
let projects=[{id:"project-1",name:"Local copy",revision:3}],selectedProject="project-1";
let reloadCount=0,openedProject="";
function projectOptions(){}
async function loadPortfolio(){reloadCount+=1}
function openProject(id){openedProject=id}
async function api(path,options={}){
 const response=await fetch(path,options);
 if(!response.ok){
  let detail="";
  try{detail=(await response.json()).error||""}catch{}
  throw new Error(detail||`Request failed (${response.status})`);
 }
 return response.json();
}
"""


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        return ApiResponse(200, _BASE_SCRIPT, "application/javascript")


class _PatchedApi(OptimisticConcurrencyWebApiMixin, _BaseApi):
    pass


def test_web050_patch_remains_managed_presentation_adapter() -> None:
    assert OptimisticConcurrencyWebApiMixin in OfflineFirstFieldoraApi.__mro__
    response = _PatchedApi().dispatch("GET", "/app.js", {}, b"")
    assert response.body.endswith(_OPTIMISTIC_CONCURRENCY_PATCH)
    script = _OPTIMISTIC_CONCURRENCY_PATCH.decode("utf-8")
    assert 'payload?.error==="revision_conflict"' in script
    assert "response.clone().json()" in script
    assert "Your attempted values" in script
    assert "Current server values" in script
    assert "Reload latest" in script
    assert "Keep editing" in script


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head></head><body><script src="/app.js"></script></body></html>',
        encoding="utf-8",
    )
    response = _PatchedApi().dispatch("GET", "/app.js", {}, b"")
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


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web050_revision_conflict_shows_compare_and_reload(
    tmp_path: Path,
    browser_name: str,
) -> None:
    current = {
        "id": "project-1",
        "name": "Server copy",
        "description": "Updated by another user",
        "revision": 4,
    }
    attempted = {
        "expected_revision": 3,
        "name": "My edit",
        "description": "Local change",
    }
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()

        def route_api(route: Route) -> None:
            request = route.request
            if request.method == "PATCH" and request.url.endswith("/api/v1/projects/project-1"):
                route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"error": "revision_conflict", "current": current}),
                )
                return
            if request.method == "GET" and "/api/v1/projects" in request.url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"items": [current]}),
                )
                return
            route.fulfill(status=404, content_type="application/json", body='{"error":"not_found"}')

        page.route("**/api/v1/**", route_api)
        page.goto(url)
        result = page.evaluate(
            """async attempted => {
              try {
                await api('/api/v1/projects/project-1', {
                  method:'PATCH', body:JSON.stringify(attempted)
                });
                return {message:'unexpected success', name:''};
              } catch (error) {
                return {message:error.message, name:error.name};
              }
            }""",
            attempted,
        )

        assert result == {
            "message": "This record changed on the server. Compare your changes or reload the latest version.",
            "name": "RevisionConflictError",
        }
        page.wait_for_selector("#revision-conflict-dialog[open]")
        assert json.loads(page.locator("#revision-conflict-local").inner_text()) == attempted
        assert json.loads(page.locator("#revision-conflict-current").inner_text()) == current

        page.locator("#revision-conflict-reload").click()
        page.wait_for_function("reloadCount === 1")
        page.wait_for_function("projects[0]?.revision === 4")
        assert page.evaluate("openedProject") == "project-1"
        assert not page.locator("#revision-conflict-dialog").evaluate("node => node.open")
        browser.close()


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web050_non_revision_conflict_stays_on_existing_error_path(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/api/v1/projects/project-1",
            lambda route: route.fulfill(
                status=409,
                content_type="application/json",
                body='{"error":"idempotency_conflict"}',
            ),
        )
        page.goto(url)
        result = page.evaluate(
            """async () => {
              try {
                await api('/api/v1/projects/project-1', {method:'PATCH', body:'{}'});
                return 'unexpected success';
              } catch (error) { return error.message; }
            }"""
        )
        assert result == "idempotency_conflict"
        assert page.locator("#revision-conflict-dialog").evaluate("node => !node.open")
        browser.close()
