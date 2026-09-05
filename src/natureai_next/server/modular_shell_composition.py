"""Explicit composition seam for registry-specific modular web shells."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server import modular_shell_web
from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleRegistry,
)

_MANIFEST_START = b" const specs="
_MANIFEST_END = b";\n const byRoute="
_DOSSIER_SENTINEL = b"WEB-DOSSIER-MODULE-COMPOSITION-SENTINEL"


def modular_shell_bootstrap(registry: WebModuleRegistry) -> bytes:
    """Return the certified shell bootstrap with metadata from ``registry``."""

    manifest = tuple(
        {
            "module_id": spec.module_id,
            "route": spec.route,
            "label": spec.label,
            "capability": spec.capability,
            "owns_actions": list(spec.owns_actions),
            "dependencies": list(spec.dependencies),
        }
        for spec in registry.as_mapping().values()
    )
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode()
    bootstrap = modular_shell_web._MODULAR_SHELL_BOOTSTRAP
    start = bootstrap.index(_MANIFEST_START) + len(_MANIFEST_START)
    end = bootstrap.index(_MANIFEST_END, start)
    return bootstrap[:start] + payload + bootstrap[end:]


def modular_shell_surface_filter(registry: WebModuleRegistry) -> bytes:
    """Remove DOM surfaces whose foundation-owned routes are not composed."""

    active_routes = {spec.route for spec in registry.as_mapping().values()}
    omitted_pages = sorted(
        spec.route.lstrip("/")
        for spec in FOUNDATION_WEB_MODULES
        if spec.route not in active_routes
    )
    payload = json.dumps(omitted_pages, ensure_ascii=False, separators=(",", ":"))
    return (
        "\n\n/* WEB-MODULAR-SHELL-COMPOSITION: prune omitted module surfaces. */\n"
        "(()=>{\n"
        f" const omitted={payload};\n"
        " omitted.forEach(page=>{\n"
        "  document.querySelectorAll(`.nav[data-page=\"${page}\"]`).forEach(node=>node.remove());\n"
        "  document.getElementById(`page-${page}`)?.remove();\n"
        " });\n"
        "})();\n"
    ).encode()


def patch_modular_shell_response(
    target: str,
    response: ApiResponse,
    *,
    registry: WebModuleRegistry,
) -> ApiResponse:
    """Apply the modular shell using an explicit registry without global mutation."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response

    body = response.body
    module_ids = registry.as_mapping()
    dossier_suppressed = "dossiers.workspace" not in module_ids
    if dossier_suppressed:
        body = body.replace(modular_shell_web._DOSSIER_OWNER_MARKER, _DOSSIER_SENTINEL)

    body = modular_shell_web._rewrite_owned_browser_response(body)

    if dossier_suppressed:
        body = body.replace(_DOSSIER_SENTINEL, modular_shell_web._DOSSIER_OWNER_MARKER)

    bootstrap = modular_shell_bootstrap(registry)
    surface_filter = modular_shell_surface_filter(registry)
    body = body.replace(
        modular_shell_web._MODULAR_SHELL_BOOTSTRAP,
        surface_filter + bootstrap,
        1,
    )
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)
