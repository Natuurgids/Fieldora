"""Browser bridge from the explicit module registry to the existing web shell.

The legacy client still owns page rendering while modules are migrated.  This
bridge does not override ``showPage`` or feature loaders.  Instead it publishes
one stable shell contract, annotates module-owned navigation/page nodes, and
emits lifecycle events that migrated modules can consume independently.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import foundation_registry


def modular_shell_manifest() -> tuple[dict[str, object], ...]:
    """Return browser-safe public module metadata in registry order."""

    registry = foundation_registry()
    return tuple(
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


def _bootstrap_script() -> bytes:
    manifest = json.dumps(modular_shell_manifest(), ensure_ascii=False, separators=(",", ":"))
    return (
        "\n\n/* WEB-MODULAR-SHELL: registry-owned navigation bridge. */\n"
        "(()=>{\n"
        " if(window.__fieldoraModularShellWired)return;window.__fieldoraModularShellWired=true;\n"
        f" const specs={manifest};\n"
        " const byRoute=new Map(specs.map(spec=>[spec.route,spec]));\n"
        " const byPage=new Map(specs.map(spec=>[spec.route.slice(1),spec]));\n"
        " const state={active:null};\n"
        " const normalize=value=>{let route=String(value||'').trim();if(!route)return '/home';"
        "if(route.startsWith('#'))route='/'+route.slice(1);if(!route.startsWith('/'))route='/'+route;"
        "route=route.split('?')[0].split('#')[0];if(route.length>1)route=route.replace(/\\/+$/,'');return route};\n"
        " const emit=(name,spec,detail={})=>document.dispatchEvent(new CustomEvent(name,{detail:{module:spec,...detail}}));\n"
        " function activate(value,source='shell'){\n"
        "  const route=normalize(value),next=byRoute.get(route);if(!next)return null;\n"
        "  const previous=state.active;if(previous&&previous.module_id===next.module_id)return next;\n"
        "  if(previous)emit('fieldora:module-unmount',previous,{source,next_module_id:next.module_id});\n"
        "  state.active=next;document.documentElement.dataset.fieldoraActiveModule=next.module_id;\n"
        "  emit('fieldora:module-mount',next,{source,previous_module_id:previous?.module_id||null});return next;\n"
        " }\n"
        " specs.forEach(spec=>{\n"
        "  const page=document.getElementById(`page-${spec.route.slice(1)}`);if(page){page.dataset.fieldoraModule=spec.module_id;page.dataset.fieldoraRoute=spec.route;}\n"
        "  document.querySelectorAll(`.nav[data-page=\"${spec.route.slice(1)}\"]`).forEach(node=>{node.dataset.fieldoraModule=spec.module_id;node.dataset.fieldoraRoute=spec.route;});\n"
        " });\n"
        " document.addEventListener('click',event=>{const nav=event.target.closest?.('.nav[data-fieldora-route]');if(nav)activate(nav.dataset.fieldoraRoute,'navigation');},true);\n"
        " window.addEventListener('hashchange',()=>activate(location.hash,'hashchange'));\n"
        " window.addEventListener('popstate',()=>activate(location.hash,'popstate'));\n"
        " window.FieldoraModules=Object.freeze({specs:Object.freeze(specs.map(spec=>Object.freeze(spec))),activate,resolve:value=>byRoute.get(normalize(value))||null,current:()=>state.active});\n"
        " activate(location.hash||'/home','bootstrap');\n"
        "})();\n"
    ).encode("utf-8")


_MODULAR_SHELL_BOOTSTRAP = _bootstrap_script()


def patch_modular_shell_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the migration bridge exactly once to the browser application."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _MODULAR_SHELL_BOOTSTRAP in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _MODULAR_SHELL_BOOTSTRAP,
        response.content_type,
        response.headers,
    )


class ModularShellWebApiMixin:
    """Outermost API mixin exposing the module registry to the real shell."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_modular_shell_response(target, response)
