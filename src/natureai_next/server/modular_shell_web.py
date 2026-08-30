"""Browser bridge from the explicit module registry to the existing web shell.

The legacy client still owns most feature rendering while modules are migrated.
This bridge publishes one stable shell contract, annotates module-owned
navigation/page nodes, owns browser route/history synchronization for registered
modules, and emits lifecycle events that migrated modules can consume
independently.

The final-response migration step also removes the old navigation compatibility
wrapper that replaced ``showPage`` solely to maintain hash history.  The shell
may call the existing renderer during migration, but it never replaces that
global function.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import foundation_registry


# Transitional removal target from navigation_web_compatibility.py.  Keeping the
# exact, narrowly scoped fragment here lets the outermost shell stop serving the
# global showPage override before the larger compatibility module is split into
# feature-owned adapters.  Once that source module is decomposed this constant
# can be deleted.
_LEGACY_HISTORY_ROUTING_PATCH = bytes(
    r"""
 const oldShowPage=showPage;
 const pageExists=name=>Boolean(q(`page-${name}`));
 let applyingHistory=false;
 showPage=function(name){
  oldShowPage(name);
  if(!applyingHistory&&pageExists(name)&&location.hash!==`#${name}`){
   history.pushState({fieldoraPage:name},"",`#${name}`);
  }
 };
 function routeFromLocation(){
  const name=(location.hash||"#home").slice(1);
  if(!pageExists(name))return;
  applyingHistory=true;try{oldShowPage(name)}finally{applyingHistory=false}
 }
 window.addEventListener("popstate",routeFromLocation);
 window.addEventListener("hashchange",routeFromLocation);
 setTimeout(routeFromLocation,0);
""",
    "utf-8",
)


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
    manifest = json.dumps(
        modular_shell_manifest(), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "\n\n/* WEB-MODULAR-SHELL: registry-owned navigation bridge. */\n"
        "(()=>{\n"
        " if(window.__fieldoraModularShellWired)return;window.__fieldoraModularShellWired=true;\n"
        f" const specs={manifest};\n"
        " const byRoute=new Map(specs.map(spec=>[spec.route,spec]));\n"
        " const state={active:null};\n"
        " const normalize=value=>{let route=String(value||'').trim();if(!route)return '/home';"
        "if(route.startsWith('#'))route='/'+route.slice(1);if(!route.startsWith('/'))route='/'+route;"
        "route=route.split('?')[0].split('#')[0];if(route.length>1)route=route.replace(/\\/+$/,'');return route};\n"
        " const emit=(name,spec,detail={})=>document.dispatchEvent(new CustomEvent(name,{detail:{module:spec,...detail}}));\n"
        " const render=spec=>{const page=spec.route.slice(1);if(typeof window.showPage==='function')window.showPage(page);};\n"
        " const writeHistory=(spec,mode)=>{const hash=`#${spec.route.slice(1)}`;if(location.hash===hash)return;"
        "const stateValue={fieldoraModule:spec.module_id,fieldoraRoute:spec.route};"
        "if(mode==='replace')history.replaceState(stateValue,'',hash);else history.pushState(stateValue,'',hash);};\n"
        " function activate(value,source='shell'){\n"
        "  const route=normalize(value),next=byRoute.get(route);if(!next)return null;\n"
        "  const previous=state.active;if(previous&&previous.module_id===next.module_id)return next;\n"
        "  if(previous)emit('fieldora:module-unmount',previous,{source,next_module_id:next.module_id});\n"
        "  state.active=next;document.documentElement.dataset.fieldoraActiveModule=next.module_id;\n"
        "  emit('fieldora:module-mount',next,{source,previous_module_id:previous?.module_id||null});return next;\n"
        " }\n"
        " function navigate(value,source='shell',historyMode='push'){const spec=activate(value,source);if(!spec)return null;render(spec);writeHistory(spec,historyMode);return spec;}\n"
        " specs.forEach(spec=>{\n"
        "  const page=document.getElementById(`page-${spec.route.slice(1)}`);if(page){page.dataset.fieldoraModule=spec.module_id;page.dataset.fieldoraRoute=spec.route;}\n"
        "  document.querySelectorAll(`.nav[data-page=\"${spec.route.slice(1)}\"]`).forEach(node=>{node.dataset.fieldoraModule=spec.module_id;node.dataset.fieldoraRoute=spec.route;});\n"
        " });\n"
        " document.addEventListener('click',event=>{const nav=event.target.closest?.('.nav[data-fieldora-route]');if(nav)navigate(nav.dataset.fieldoraRoute,'navigation','push');},true);\n"
        " const restore=source=>{const spec=activate(location.hash||'/home',source);if(spec)render(spec);};\n"
        " window.addEventListener('hashchange',()=>restore('hashchange'));\n"
        " window.addEventListener('popstate',()=>restore('popstate'));\n"
        " window.FieldoraModules=Object.freeze({specs:Object.freeze(specs.map(spec=>Object.freeze(spec))),activate,navigate,resolve:value=>byRoute.get(normalize(value))||null,current:()=>state.active});\n"
        " const initial=activate(location.hash||'/home','bootstrap');if(initial){render(initial);if(!location.hash)writeHistory(initial,'replace');}\n"
        "})();\n"
    ).encode("utf-8")


_MODULAR_SHELL_BOOTSTRAP = _bootstrap_script()


def patch_modular_shell_response(target: str, response: ApiResponse) -> ApiResponse:
    """Migrate route/history ownership and append the shell exactly once."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response

    body = response.body.replace(_LEGACY_HISTORY_ROUTING_PATCH, b"", 1)
    if _MODULAR_SHELL_BOOTSTRAP not in body:
        body += _MODULAR_SHELL_BOOTSTRAP
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)


class ModularShellWebApiMixin:
    """Outermost API mixin exposing the module registry to the real shell."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_modular_shell_response(target, response)
