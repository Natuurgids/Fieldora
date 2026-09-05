from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Route, sync_playwright

from natureai_next.server import modular_shell_composition, web_module_contract_runtime
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import patch_browser_functionality_response
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response
from natureai_next.server.web_compatibility import patch_web_response
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleRegistry,
    WebModuleSpec,
)

_PROJECT_MODULES = {
    "projects.core",
    "portfolio",
    "capacity",
    "research.dossiers",
    "dossiers.workspace",
}
_PROJECT_ROUTES = {
    "/projects",
    "/portfolio",
    "/capacity",
    "/research",
    "/dossiers",
}
_PROJECT_CONTRACTS = {
    "projects.list.read",
    "projects.context.select",
    "projects.toolbar.extend",
}
_REPLACEMENT_PROVIDER = b"""
/* TEST-PROJECTS-REPLACEMENT: minimal public-contract implementation. */
(()=>{
 const contracts=window.FieldoraModuleContracts;
 const state={
  items:[{id:"replacement-1",name:"Replacement project",owner_id:"admin-1",status:"active"}],
  selected:"",extensions:[]
 };
 contracts.register("projects.list.read","projects.replacement",Object.freeze({
  items:()=>state.items.map(item=>({...item})),
  refresh:async()=>state.items.map(item=>({...item})),
  loaded:()=>true
 }));
 contracts.register("projects.context.select","projects.replacement",Object.freeze({
  current:()=>state.selected,
  select:id=>{state.selected=String(id||"");return true}
 }));
 contracts.register("projects.toolbar.extend","projects.replacement",Object.freeze({
  register:extension=>{state.extensions.push(extension);return ()=>{}},
  items:()=>[...state.extensions]
 }));
 window.FieldoraReplacementProjects=Object.freeze({
  selected:()=>state.selected,
  extensionCount:()=>state.extensions.length
 });
})();
"""


def _projects_free_registry() -> WebModuleRegistry:
    registry = WebModuleRegistry(
        spec for spec in FOUNDATION_WEB_MODULES if spec.module_id not in _PROJECT_MODULES
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry


def _replacement_projects_registry() -> WebModuleRegistry:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Projects replacement",
        provides_contracts=tuple(sorted(_PROJECT_CONTRACTS)),
    )
    registry = WebModuleRegistry(
        replacement if spec.module_id == "projects.core" else spec
        for spec in FOUNDATION_WEB_MODULES
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry


def _patched_app(registry: WebModuleRegistry, *, portfolio: bool = False) -> ApiResponse:
    resource = Path("src/natureai_next/resources/server_web")
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
    ):
        response = patch("/app.js", response)
    if portfolio:
        response = patch_portfolio_module_response("/app.js", response)
    response = modular_shell_composition.patch_modular_shell_response(
        "/app.js", response, registry=registry
    )
    return web_module_contract_runtime.patch_runtime_contracts_response(
        "/app.js", response, registry=registry
    )


@contextlib.contextmanager
def _serve_web(tmp_path: Path, response: ApiResponse):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
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


@contextlib.contextmanager
def _projects_free_web(tmp_path: Path):
    with _serve_web(tmp_path, _patched_app(_projects_free_registry())) as url:
        yield url


@contextlib.contextmanager
def _replacement_projects_web(tmp_path: Path):
    response = _patched_app(_replacement_projects_registry(), portfolio=True)
    response = ApiResponse(
        response.status,
        response.body + _REPLACEMENT_PROVIDER,
        response.content_type,
        response.headers,
    )
    with _serve_web(tmp_path, response) as url:
        yield url


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


def test_projects_free_browser_boots_and_keeps_unrelated_library_action(tmp_path: Path) -> None:
    with _projects_free_web(tmp_path) as url, sync_playwright() as playwright:
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

        for route in _PROJECT_ROUTES:
            page_name = route.lstrip("/")
            assert not page.evaluate("route=>Boolean(FieldoraModules.resolve(route))", route)
            assert page.locator(f'.nav[data-page="{page_name}"]').count() == 0
            assert page.locator(f"#page-{page_name}").count() == 0

        assert page.evaluate("Boolean(FieldoraModules.resolve('/library'))")
        assert page.locator('.nav[data-page="library"]').count() == 1
        assert page.locator("#page-library").count() == 1
        page.locator('.nav[data-page="library"]').click()
        page.wait_for_selector("#page-library:not([hidden])")
        page.locator('[data-media-filter="image"]').click()
        assert page.locator('[data-media-filter="image"]').evaluate(
            "node=>node.classList.contains('primary')"
        )
        assert page.locator("#media-grid").is_visible()
        browser.close()


def test_replacement_projects_provider_drives_unchanged_portfolio_consumer(
    tmp_path: Path,
) -> None:
    with _replacement_projects_web(tmp_path) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", _api)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','projects-replacement-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        assert page.evaluate("FieldoraModules.resolve('/projects').module_id") == (
            "projects.replacement"
        )
        for contract in _PROJECT_CONTRACTS:
            assert page.evaluate(
                "contract=>FieldoraModuleContracts.provider(contract)", contract
            ) == "projects.replacement"
        assert page.evaluate("FieldoraModuleContracts.unresolved('portfolio')") == []

        page.locator('.nav[data-page="projects"]').click()
        page.wait_for_selector("#page-projects:not([hidden])")
        page.evaluate("FieldoraPortfolio.mount()")
        replacement = page.locator(
            '#portfolio-list [data-portfolio-id="replacement-1"][data-kind="project"]'
        )
        replacement.wait_for()
        assert "Replacement project" in replacement.inner_text()
        replacement.click()
        assert page.evaluate("FieldoraReplacementProjects.selected()") == "replacement-1"
        browser.close()
