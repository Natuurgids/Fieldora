from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Route, sync_playwright

from natureai_next.server import modular_shell_web, web_module_contract_runtime
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import patch_browser_functionality_response
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.web_compatibility import patch_web_response
from natureai_next.server.web_module_contracts import FOUNDATION_WEB_MODULES, WebModuleRegistry

_PROJECT_MODULES = {
    "projects.core",
    "portfolio",
    "capacity",
    "research.dossiers",
    "dossiers.workspace",
}
_PROJECT_CONTRACTS = {
    "projects.list.read",
    "projects.context.select",
    "projects.toolbar.extend",
}


def _projects_free_registry() -> WebModuleRegistry:
    registry = WebModuleRegistry(
        spec for spec in FOUNDATION_WEB_MODULES if spec.module_id not in _PROJECT_MODULES
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry


@contextlib.contextmanager
def _projects_free_web(tmp_path: Path, monkeypatch):
    registry = _projects_free_registry()
    monkeypatch.setattr(modular_shell_web, "foundation_registry", lambda: registry)
    monkeypatch.setattr(
        modular_shell_web, "_MODULAR_SHELL_BOOTSTRAP", modular_shell_web._bootstrap_script()
    )

    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    for patch in (
        patch_contract_web_response,
        patch_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
        patch_browser_functionality_response,
        modular_shell_web.patch_modular_shell_response,
    ):
        response = patch("/app.js", response)
    response = web_module_contract_runtime.patch_runtime_contracts_response(
        "/app.js", response, registry=registry
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


def _api(route: Route) -> None:
    parsed = urlsplit(route.request.url)
    path = parsed.path.split("/api/v1/", 1)[-1]
    if path == "me":
        payload: object = {
            "identity_id": "admin-1",
            "display_name": "Administrator",
            "organization_id": "local",
        }
    elif path == "runtime":
        payload = {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}}
    else:
        payload = {"items": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def test_projects_free_browser_boots_and_keeps_unrelated_library_action(
    tmp_path: Path, monkeypatch
) -> None:
    with _projects_free_web(tmp_path, monkeypatch) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','projects-free-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        module_ids = page.evaluate("FieldoraModules.specs.map(spec=>spec.module_id)")
        assert not (_PROJECT_MODULES & set(module_ids))
        declarations = page.evaluate(
            "FieldoraModuleContracts.declarations.map(spec=>spec.module_id)"
        )
        assert not (_PROJECT_MODULES & set(declarations))
        for contract in _PROJECT_CONTRACTS:
            assert page.evaluate("contract=>FieldoraModuleContracts.provider(contract)", contract) is None

        assert page.evaluate("Boolean(FieldoraModules.resolve('/library'))")
        page.locator('.nav[data-page="library"]').click()
        page.wait_for_selector("#page-library:not([hidden])")
        page.locator('[data-media-filter="image"]').click()
        assert page.locator('[data-media-filter="image"]').evaluate(
            "node=>node.classList.contains('primary')"
        )
        assert page.locator("#media-grid").is_visible()
        browser.close()
