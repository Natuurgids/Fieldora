"""Browser bridge from the explicit module registry to the existing web shell.

The legacy client still owns most feature rendering while modules are migrated.
This bridge publishes one stable shell contract, annotates module-owned
navigation/page nodes, owns browser route/history synchronization for registered
modules, and emits lifecycle events that migrated modules can consume
independently.

The final-response migration step removes compatibility fragments only after an
owning module exists for that responsibility. The shell may call the existing
renderer during migration, but it never replaces that global function.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_hierarchy_web import _PROJECT_HIERARCHY_PATCH
from natureai_next.server.project_lifecycle_web import _PROJECT_LIFECYCLE_WEB_PATCH
from natureai_next.server.project_runtime_web import _PROJECT_RUNTIME_WEB_PATCH
from natureai_next.server.web_module_contracts import foundation_registry

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
_LEGACY_HISTORY_ROUTING_START = b" const oldShowPage=showPage;"
_LEGACY_HISTORY_ROUTING_END = b" function selectTab(buttons,selected){"

_LEGACY_PORTFOLIO_START = b" /* Projects & Portfolio used to change only the selected button.  Render a\n"
_LEGACY_PORTFOLIO_END = b" /* Knowledge tabs previously had no state or handlers at all. */"
_LEGACY_PORTFOLIO_REFRESH_WIRING = b'q("portfolio-refresh").onclick=loadPortfolio;'
_LEGACY_PORTFOLIO_SCOPE_WIRING = b'q("portfolio-scope").onchange=loadPortfolio;'
_LEGACY_PORTFOLIO_VIEW_WIRING = b'document.querySelectorAll("[data-portfolio-view]").forEach(b=>b.onclick=()=>{portfolioView=b.dataset.portfolioView;document.querySelectorAll("[data-portfolio-view]").forEach(x=>x.classList.toggle("primary",x===b));loadPortfolio()});'
_LEGACY_PROJECTS_SHOWPAGE_LOAD = b'if(name==="projects")loadPortfolio();'
_LEGACY_WORK_SAVE_REFRESH = b'if(await saveGeneric(path,item,"work-status",`${type} saved.`))loadPortfolio()'
_PROJECT_EVENT_WORK_SAVE_REFRESH = b'if(await saveGeneric(path,item,"work-status",`${type} saved.`))document.dispatchEvent(new CustomEvent("fieldora:project-work-changed",{detail:{module_id:"legacy.work-editor",project_id:project,kind:type,item:null}}))'
_LEGACY_PORTFOLIO_LOADER_START = b"async function loadPortfolio(){"
_LEGACY_PORTFOLIO_LOADER_END = b"async function saveWorkItem(){"
_LEGACY_RESEARCH_PROJECT_LIST_START = b'cards("project-list",projects,'
_LEGACY_RESEARCH_PROJECT_LIST_END = b'cards("dossier-list",dossiers,'
_LEGACY_RESEARCH_PROJECT_LIST_WIRING = (
    b'q("project-list").onclick=e=>{const row=e.target.closest("[data-project]");if(row)openProject(row.dataset.project)};'
)
_LEGACY_RESEARCH_SELECTED_PROJECT_WRITE = b"function openProject(id){selectedProject=id;"
_LEGACY_DOSSIER_LOADER_START = b"async function loadDossierWorkspace(){"
_LEGACY_DOSSIER_LOADER_END = b"async function loadResearchDomain(){"
_LEGACY_DOSSIER_REFRESH_WIRING = b'q("dossier-refresh").onclick=loadDossierWorkspace;'
_LEGACY_DOSSIER_SAVE_WIRING = b'q("dossier-save").onclick=saveDossierWorkspace;'
_LEGACY_DOSSIER_LIST_WIRING = b'q("dossier-workspace-list").onclick=e=>{const row=e.target.closest("[data-dossier-workspace]");if(!row)return;const dossiers=JSON.parse(q("dossier-workspace-list").dataset.records||"[]"),reviews=JSON.parse(q("dossier-workspace-list").dataset.reviews||"[]"),d=dossiers.find(x=>x.id===row.dataset.dossierWorkspace);q("dossier-workspace-detail").innerHTML=`<h3>${esc(recordName(d||{}))}</h3><pre>${esc(JSON.stringify(d,null,2))}</pre><h4>Review history</h4><pre>${esc(JSON.stringify(reviews.filter(r=>r.dossier_id===d?.id),null,2))}</pre>`};'
_PORTFOLIO_OWNER_MARKER = b"WEB-PORTFOLIO-MODULE"
_PROJECT_OWNER_MARKER = b"WEB-PROJECT-CORE-MODULE"
_PROJECT_CREATION_OWNER_MARKER = b"WEB-PROJECT-CREATION-MODULE"
_PROJECT_LIFECYCLE_OWNER_MARKER = b"WEB-PROJECT-LIFECYCLE-MODULE"
_PROJECT_WORK_ACTIONS_OWNER_MARKER = b"WEB-PROJECT-WORK-ACTIONS-MODULE"
_PROJECT_EVIDENCE_ACTIONS_OWNER_MARKER = b"WEB-PROJECT-EVIDENCE-ACTIONS-MODULE"
_RESEARCH_OWNER_MARKER = b"WEB-PROJECT-RESEARCH-INTEGRATION"
_DOSSIER_OWNER_MARKER = b"WEB-DOSSIER-MODULE"
_DOSSIER_REGISTRY_MARKER = b'"module_id":"dossiers.workspace"'

# Project creation first shipped inside the general browser-functionality patch.
# Remove only that bounded fragment once Projects/Core has its dedicated owner.
_LEGACY_PROJECT_CREATION_START = (
    b" /* Project creation belongs in Projects & Portfolio as well as Research. */"
)
_LEGACY_PROJECT_CREATION_END = b" function setIndicator(id,text){"

# The desktop-density Projects/Facilities cockpit predates explicit module
# ownership. Portfolio and Projects/Core are removed in separate marker-bounded
# ranges so either module can be replaced without deleting the other's fallback.
_PROJECT_COCKPIT_PORTFOLIO_RENDER_START = b" function portfolioData(){"
_PROJECT_COCKPIT_PORTFOLIO_RENDER_END = b" function setProjectCenter(view){"
_PROJECT_COCKPIT_PORTFOLIO_WIRING_START = b"  const oldPortfolio=loadPortfolio;"
_PROJECT_COCKPIT_PORTFOLIO_WIRING_END = b'  q("portfolio-list").addEventListener("click"'
_PROJECT_COCKPIT_BEHAVIOR_START = b' let cockpitProjectId="";'
_PROJECT_COCKPIT_BEHAVIOR_END = b" function portfolioData(){"
_PROJECT_COCKPIT_CENTER_START = b" function setProjectCenter(view){"
_PROJECT_COCKPIT_CENTER_END = b' if(projectPage&&!q("project-desktop-cockpit")){'
_PROJECT_COCKPIT_WIRING_START = b'  q("project-tree-filter").oninput=renderProjectTree;'
_PROJECT_COCKPIT_WIRING_END = b"  const oldPortfolio=loadPortfolio;"
_PROJECT_COCKPIT_WORK_WIRING_START = b'  q("portfolio-list").addEventListener("click"'
_PROJECT_COCKPIT_WORK_WIRING_END = b" }\n\n /* ---- Facility / CMDB cockpit"


def _strip_legacy_range(body: bytes, start: bytes, end: bytes) -> bytes:
    """Remove one migrated compatibility responsibility by stable markers."""

    start_index = body.find(start)
    if start_index < 0:
        return body
    end_index = body.find(end, start_index)
    if end_index < 0:
        return body
    return body[:start_index] + body[end_index:]


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
    ).encode()


_MODULAR_SHELL_BOOTSTRAP = _bootstrap_script()


def _rewrite_owned_browser_response(body: bytes) -> bytes:
    """Remove only responsibilities whose replacement owner is present."""

    body = body.replace(_LEGACY_HISTORY_ROUTING_PATCH, b"", 1)
    body = _strip_legacy_range(
        body, _LEGACY_HISTORY_ROUTING_START, _LEGACY_HISTORY_ROUTING_END
    )
    if _PORTFOLIO_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body, _LEGACY_PORTFOLIO_START, _LEGACY_PORTFOLIO_END
        )
        body = body.replace(_LEGACY_PORTFOLIO_REFRESH_WIRING, b"", 1)
        body = body.replace(_LEGACY_PORTFOLIO_SCOPE_WIRING, b"", 1)
        body = body.replace(_LEGACY_PORTFOLIO_VIEW_WIRING, b"", 1)
    if _PROJECT_OWNER_MARKER in body:
        # Managed Project APIs remain authoritative; only browser competitors are
        # retired after their Projects/Core replacements are present. Strip the
        # leading Project cockpit behavior before Portfolio consumes its end marker.
        body = body.replace(_LEGACY_PROJECTS_SHOWPAGE_LOAD, b"", 1)
        body = body.replace(_LEGACY_WORK_SAVE_REFRESH, _PROJECT_EVENT_WORK_SAVE_REFRESH, 1)
        body = body.replace(_PROJECT_HIERARCHY_PATCH, b"", 1)
        body = _strip_legacy_range(
            body, _PROJECT_COCKPIT_BEHAVIOR_START, _PROJECT_COCKPIT_BEHAVIOR_END
        )
    if _PORTFOLIO_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body,
            _PROJECT_COCKPIT_PORTFOLIO_RENDER_START,
            _PROJECT_COCKPIT_PORTFOLIO_RENDER_END,
        )
    if _PROJECT_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body, _PROJECT_COCKPIT_CENTER_START, _PROJECT_COCKPIT_CENTER_END
        )
        body = _strip_legacy_range(
            body, _PROJECT_COCKPIT_WIRING_START, _PROJECT_COCKPIT_WIRING_END
        )
    if _PORTFOLIO_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body,
            _PROJECT_COCKPIT_PORTFOLIO_WIRING_START,
            _PROJECT_COCKPIT_PORTFOLIO_WIRING_END,
        )
    if _PROJECT_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body, _PROJECT_COCKPIT_WORK_WIRING_START, _PROJECT_COCKPIT_WORK_WIRING_END
        )
    if _PROJECT_OWNER_MARKER in body and _PORTFOLIO_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body, _LEGACY_PORTFOLIO_LOADER_START, _LEGACY_PORTFOLIO_LOADER_END
        )
    if _RESEARCH_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body,
            _LEGACY_RESEARCH_PROJECT_LIST_START,
            _LEGACY_RESEARCH_PROJECT_LIST_END,
        )
        body = body.replace(_LEGACY_RESEARCH_PROJECT_LIST_WIRING, b"", 1)
        body = body.replace(_LEGACY_RESEARCH_SELECTED_PROJECT_WRITE, b"function openProject(id){", 1)
    if _PROJECT_CREATION_OWNER_MARKER in body:
        body = _strip_legacy_range(
            body, _LEGACY_PROJECT_CREATION_START, _LEGACY_PROJECT_CREATION_END
        )
    if _PROJECT_LIFECYCLE_OWNER_MARKER in body:
        body = body.replace(_PROJECT_LIFECYCLE_WEB_PATCH, b"", 1)
    if (
        _PROJECT_WORK_ACTIONS_OWNER_MARKER in body
        and _PROJECT_EVIDENCE_ACTIONS_OWNER_MARKER in body
    ):
        body = body.replace(_PROJECT_RUNTIME_WEB_PATCH, b"", 1)
    if _DOSSIER_OWNER_MARKER in body and _DOSSIER_REGISTRY_MARKER in _MODULAR_SHELL_BOOTSTRAP:
        body = _strip_legacy_range(
            body, _LEGACY_DOSSIER_LOADER_START, _LEGACY_DOSSIER_LOADER_END
        )
        body = body.replace(_LEGACY_DOSSIER_REFRESH_WIRING, b"", 1)
        body = body.replace(_LEGACY_DOSSIER_SAVE_WIRING, b"", 1)
        body = body.replace(_LEGACY_DOSSIER_LIST_WIRING, b"", 1)
    body = body.replace(_MODULAR_SHELL_BOOTSTRAP, b"", 1)
    return body + _MODULAR_SHELL_BOOTSTRAP


def patch_modular_shell_response(target: str, response: ApiResponse) -> ApiResponse:
    """Install the shell and remove compatibility code with replacement owners."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = _rewrite_owned_browser_response(response.body)
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)


def finalize_modular_shell_response(target: str, response: ApiResponse) -> ApiResponse:
    """Finalize an already-modular response after HTTP compatibility patches."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _MODULAR_SHELL_BOOTSTRAP not in response.body
    ):
        return response
    body = _rewrite_owned_browser_response(response.body)
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
