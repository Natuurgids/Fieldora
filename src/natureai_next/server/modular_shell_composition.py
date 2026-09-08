"""Explicit composition seam for registry-specific modular web shells."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from natureai_next.server import modular_shell_web
from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_module_composition import (
    suppress_facilities_browser_response,
)
from natureai_next.server.web_module_contracts import (
    FOUNDATION_APPLICATION_CONTRACT_PROVIDERS,
    FOUNDATION_WEB_MODULES,
    WebModuleContractError,
    WebModuleRegistry,
)
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    FOUNDATION_WEB_MODULE_EXTENSIONS,
    WebModuleExtensionSpec,
)

_MANIFEST_START = b" const specs="
_MANIFEST_END = b";\n const byRoute="
_DOSSIER_SENTINEL = b"WEB-DOSSIER-MODULE-COMPOSITION-SENTINEL"


class FoundationCompositionRegistry(WebModuleRegistry):
    """Foundation registry plus truthful non-route module extension identities."""

    def __init__(
        self,
        specs=(),
        *,
        extensions: Iterable[WebModuleExtensionSpec] = (),
    ) -> None:
        super().__init__(
            specs,
            application_providers=FOUNDATION_APPLICATION_CONTRACT_PROVIDERS,
        )
        self._extensions = {extension.module_id: extension for extension in extensions}

    def extension_mapping(self) -> Mapping[str, WebModuleExtensionSpec]:
        return dict(self._extensions)

    def is_composed(self, module_id: str) -> bool:
        normalized = module_id.strip()
        return normalized in self.as_mapping() or normalized in self._extensions


def foundation_composition_registry(
    enabled_module_ids: Iterable[str] | None = None,
) -> WebModuleRegistry:
    """Return a validated foundation registry containing only enabled modules."""

    route_ids = {spec.module_id for spec in FOUNDATION_WEB_MODULES}
    extension_ids = {spec.module_id for spec in FOUNDATION_WEB_MODULE_EXTENSIONS}
    known_ids = route_ids | extension_ids
    if enabled_module_ids is None:
        enabled_ids = known_ids
    else:
        enabled_ids = {module_id.strip() for module_id in enabled_module_ids}
        if "" in enabled_ids:
            raise WebModuleContractError("enabled module ids may not be blank")
        unknown = sorted(enabled_ids - known_ids)
        if unknown:
            raise WebModuleContractError(f"unknown enabled module ids: {unknown!r}")

    registry = FoundationCompositionRegistry(
        tuple(spec for spec in FOUNDATION_WEB_MODULES if spec.module_id in enabled_ids),
        extensions=tuple(
            spec for spec in FOUNDATION_WEB_MODULE_EXTENSIONS if spec.module_id in enabled_ids
        ),
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry


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
            "provides_contracts": list(spec.provides_contracts),
            "requires_contracts": list(spec.requires_contracts),
            "optional_contracts": list(spec.optional_contracts),
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


def _extension_is_composed(registry: WebModuleRegistry, module_id: str) -> bool:
    checker = getattr(registry, "is_composed", None)
    if callable(checker):
        return bool(checker(module_id))
    # Plain registries predate extension identities. Preserve their historical
    # behavior rather than silently suppressing browser functionality.
    return True


def finalize_modular_shell_response(
    target: str,
    response: ApiResponse,
    *,
    registry: WebModuleRegistry | None = None,
) -> ApiResponse:
    """Finalize an installed shell with the production composition registry."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or modular_shell_web._MODULAR_SHELL_BOOTSTRAP not in response.body
    ):
        return response
    selected_registry = foundation_composition_registry() if registry is None else registry
    if not _extension_is_composed(selected_registry, FACILITIES_WEB_MODULE_ID):
        response = suppress_facilities_browser_response(target, response)
    return patch_modular_shell_response(target, response, registry=selected_registry)
