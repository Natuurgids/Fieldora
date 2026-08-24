from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.http import patch_managed_web_response


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    response = patch_managed_web_response("/app.js", response)
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
def test_offline_model_artifact_registers_through_governed_ai_models(
    tmp_path: Path,
    browser_name: str,
) -> None:
    registered: list[dict[str, object]] = []
    administration_requests: list[tuple[str, str]] = []
    artifact = {
        "id": "bio-model@1.2.3",
        "model_id": "bio-model",
        "name": "Biodiversity model",
        "version": "1.2.3",
        "project_id": "platform",
        "provider_id": "fieldora-offline",
        "network": "offline",
        "status": "installed",
        "artifact_storage_id": "model:bio-model:1.2.3",
        "artifact_total_bytes": 1073741824,
        "source": "fieldora-bastion",
        "license_id": "test-license",
        "verification": "sha256-per-file",
        "formats": ["safetensors"],
    }

    def mock_api(route: Route) -> None:
        request = route.request
        path = request.url.split("/api/v1/", 1)[-1].split("?", 1)[0]
        if path in {"ai-providers", "ai-models", "ai-models/installed", "mcp-servers"}:
            administration_requests.append(
                (path, request.headers.get("x-fieldora-purpose", ""))
            )
        if path == "me":
            payload: object = {
                "identity_id": "admin-1",
                "display_name": "Administrator",
                "organization_id": "local",
            }
        elif path == "projects":
            payload = {"items": []}
        elif path == "runtime":
            payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
        elif path == "dossiers":
            payload = {"items": []}
        elif path == "ai-models/installed":
            payload = {"items": [artifact], "count": 1}
        elif path == "ai-models" and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            registered.append(body)
            payload = {"item": body, "revision": 1}
        elif path == "ai-models":
            payload = {"items": registered, "count": len(registered)}
        elif path in {"ai-providers", "mcp-servers"}:
            payload = {"items": []}
        else:
            payload = {"items": []}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", mock_api)
        page.add_init_script("sessionStorage.setItem('fieldora-session','offline-model-certification')")
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")
        page.evaluate("showPage('aiadmin'); loadAIAdministration()")

        section = page.locator("#offline-model-artifacts")
        section.wait_for(state="visible")
        assert "Biodiversity model" in section.inner_text()
        assert "1.2.3" in section.inner_text()
        assert "/var/lib/fieldora-models" not in section.inner_text()
        assert administration_requests
        assert all(purpose == "administration" for _path, purpose in administration_requests)

        section.get_by_role("button", name="Register & enable", exact=True).click()
        page.wait_for_function(
            "() => document.querySelector('#offline-model-artifacts button')?.textContent === 'Registered'"
        )
        assert len(registered) == 1
        record = registered[0]
        assert record["id"] == "bio-model@1.2.3"
        assert record["project_id"] == "platform"
        assert record["artifact_storage_id"] == "model:bio-model:1.2.3"
        assert record["enabled"] is True
        assert "artifact_store_path" not in record
        assert "/var/lib/fieldora-models" not in json.dumps(record)
        assert all(purpose == "administration" for _path, purpose in administration_requests)
        browser.close()
