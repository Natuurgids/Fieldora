from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.optimistic_concurrency_web import OptimisticConcurrencyWebApiMixin
from natureai_next.server.structured_errors import (
    _STRUCTURED_ERROR_WEB_PATCH,
    StructuredErrorApiMixin,
    structured_error_response,
)

_BASE_SCRIPT = b"""
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
        if target == "/app.js":
            return ApiResponse(200, _BASE_SCRIPT, "application/javascript")
        return ApiResponse.json(404, {"error": "not_found"})


class _PatchedApi(StructuredErrorApiMixin, _BaseApi):
    pass


class _CombinedApi(OptimisticConcurrencyWebApiMixin, StructuredErrorApiMixin, _BaseApi):
    pass


def test_structured_error_envelope_keeps_legacy_fields_and_adds_safe_contract() -> None:
    response = structured_error_response(
        ApiResponse.json(
            409,
            {
                "error": "revision_conflict",
                "detail": "internal row version 839 belongs to tenant secret",
                "current": {"id": "project-1", "revision": 4},
            },
        )
    )
    payload = json.loads(response.body)

    assert response.status == 409
    assert payload["error"] == "revision_conflict"
    assert payload["code"] == "revision_conflict"
    assert payload["current"] == {"id": "project-1", "revision": 4}
    assert "tenant secret" not in payload["message"]
    UUID(payload["correlation_id"])
    assert dict(response.headers)["X-Correlation-ID"] == payload["correlation_id"]


def test_structured_error_envelope_handles_non_json_failures() -> None:
    response = structured_error_response(ApiResponse(503, b"upstream exploded", "text/plain"))
    payload = json.loads(response.body)

    assert payload["code"] == "request_failed"
    assert "upstream exploded" not in payload["message"]
    UUID(payload["correlation_id"])


def test_web051_composition_sits_below_web050_and_patch_is_packaged() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    assert mro.index(OptimisticConcurrencyWebApiMixin) < mro.index(StructuredErrorApiMixin)
    response = _PatchedApi().dispatch("GET", "/app.js", {}, b"")
    assert response.body.endswith(_STRUCTURED_ERROR_WEB_PATCH)
    script = _STRUCTURED_ERROR_WEB_PATCH.decode("utf-8")
    assert '"transport","network_error"' in script
    assert 'if(status===401||status===403)return "auth"' in script
    assert 'if(status===409)return "conflict"' in script
    assert 'return "validation"' in script
    assert "X-Correlation-ID" in script
    assert "fieldoraErrorSummary" in script


@contextlib.contextmanager
def _web_fixture(tmp_path: Path, api_type=_PatchedApi):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="/app.js"></script></body></html>',
        encoding="utf-8",
    )
    response = api_type().dispatch("GET", "/app.js", {}, b"")
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
def test_web051_browser_distinguishes_auth_validation_conflict_and_transport(
    tmp_path: Path,
    browser_name: str,
) -> None:
    cases = {
        "auth": (401, "unauthorized", "auth"),
        "validation": (400, "invalid_request", "validation"),
        "conflict": (409, "revision_conflict", "conflict"),
        "server": (503, "unavailable", "server"),
    }
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()

        def route_api(route: Route) -> None:
            key = route.request.url.rsplit("/", 1)[-1]
            if key == "transport":
                route.abort("failed")
                return
            status_code, code, _kind = cases[key]
            route.fulfill(
                status=status_code,
                content_type="application/json",
                headers={"X-Correlation-ID": f"corr-{key}"},
                body=json.dumps(
                    {
                        "error": code,
                        "code": code,
                        "message": f"Safe {key} message",
                        "correlation_id": f"corr-{key}",
                    }
                ),
            )

        page.route("**/api/v1/**", route_api)
        page.goto(url)
        result = page.evaluate(
            """async keys => {
              const output={};
              for(const key of keys){
                try{await api(`/api/v1/${key}`);output[key]={kind:'success'};}
                catch(error){
                  output[key]={
                    kind:error.kind,
                    code:error.code,
                    message:error.message,
                    correlationId:error.correlationId,
                    summary:window.fieldoraErrorSummary(error),
                  };
                }
              }
              return output;
            }""",
            [*cases, "transport"],
        )

        for key, (_status, code, kind) in cases.items():
            assert result[key]["kind"] == kind
            assert result[key]["code"] == code
            assert result[key]["message"] == f"Safe {key} message"
            assert result[key]["correlationId"] == f"corr-{key}"
            assert f"reference corr-{key}" in result[key]["summary"]
        assert result["transport"] == {
            "kind": "transport",
            "code": "network_error",
            "message": "The server could not be reached. Check the connection and try again.",
            "correlationId": "",
            "summary": "The server could not be reached. Check the connection and try again.",
        }
        browser.close()


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web051_structured_revision_conflict_still_reaches_web050_compare_ux(
    tmp_path: Path,
    browser_name: str,
) -> None:
    current = {"id": "project-1", "name": "Server copy", "revision": 4}
    attempted = {"expected_revision": 3, "name": "My edit"}
    with _web_fixture(tmp_path, _CombinedApi) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/api/v1/projects/project-1",
            lambda route: route.fulfill(
                status=409,
                content_type="application/json",
                headers={"X-Correlation-ID": "corr-conflict"},
                body=json.dumps(
                    {
                        "error": "revision_conflict",
                        "code": "revision_conflict",
                        "message": "The request conflicts with the current server state.",
                        "correlation_id": "corr-conflict",
                        "current": current,
                    }
                ),
            ),
        )
        page.goto(url)
        result = page.evaluate(
            """async attempted => {
              try{
                await api('/api/v1/projects/project-1', {
                  method:'PATCH', body:JSON.stringify(attempted)
                });
                return {name:'unexpected success',message:''};
              }catch(error){return {name:error.name,message:error.message};}
            }""",
            attempted,
        )

        assert result == {
            "name": "RevisionConflictError",
            "message": "This record changed on the server. Compare your changes or reload the latest version.",
        }
        page.wait_for_selector("#revision-conflict-dialog[open]")
        assert json.loads(page.locator("#revision-conflict-local").inner_text()) == attempted
        assert json.loads(page.locator("#revision-conflict-current").inner_text()) == current
        browser.close()
