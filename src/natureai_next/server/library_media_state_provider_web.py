"""Library-owned media state provider for the managed web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import WebModuleRegistry

_NAVIGATION_MEDIA_FILTER_TABS = b'["media-filter","observation-filter","research-domain"]'
_NAVIGATION_NON_LIBRARY_TABS = b'["observation-filter","research-domain"]'

_LIBRARY_MEDIA_STATE_PROVIDER_PATCH = bytes(
    r"""

/* WEB-LIBRARY-MEDIA-STATE-PROVIDER: Library-owned immutable media state. */
(()=>{
 if(window.__fieldoraLibraryMediaStateProviderWired)return;
 window.__fieldoraLibraryMediaStateProviderWired=true;
 const pageSize=50;
 let items=Object.freeze([]),filter="all",cursor="";
 const freezeItems=value=>Object.freeze((Array.isArray(value)?value:[]).map(item=>item&&typeof item==="object"?Object.freeze({...item}):item));
 const snapshot=()=>Object.freeze({module_id:"library.catalog",items,filter});
 const publish=()=>{const value=snapshot();document.dispatchEvent(new CustomEvent("fieldora:library-media-state-changed",{detail:value}));return value;};
 const replaceItems=(value,reset)=>{items=freezeItems(reset?value:[...items,...(Array.isArray(value)?value:[])]);return publish();};
 const queryValue=()=>String(document.querySelector("#page-library .global-search")?.value||"").trim();
 const syncFilterButtons=()=>document.querySelectorAll("[data-media-filter]").forEach(button=>{const active=String(button.dataset.mediaFilter||"all")===filter;button.classList.toggle("primary",active);button.setAttribute("aria-selected",String(active));button.setAttribute("role","tab");});
 const pager=()=>{const node=document.getElementById("media-grid");if(!node)return;let button=document.getElementById("media-load-more");if(!button){button=document.createElement("button");button.id="media-load-more";button.textContent="Load more";button.className="section";node.insertAdjacentElement("afterend",button)}button.hidden=!cursor;button.onclick=()=>load(false);};
 async function load(reset=true){try{const search=queryValue(),kind=filter==="all"?"":filter;const params=new URLSearchParams({limit:String(pageSize)});if(search)params.set("q",search);if(kind)params.set("kind",kind);if(!reset&&cursor)params.set("after",cursor);const result=await api(`/api/v1/media?${params}`);replaceItems(result?.items||[],reset);cursor=String(result?.next_cursor||"");renderMedia();pager();return snapshot()}catch(error){cards("media-grid",[],x=>x,error.message);return snapshot()}}
 const selectFilter=async value=>{filter=String(value||"all");publish();syncFilterButtons();renderMedia();return load(true);};
 loadMedia=async function(reset=true){return load(reset);};
 document.querySelectorAll("[data-media-filter]").forEach(button=>{button.onclick=()=>selectFilter(button.dataset.mediaFilter);});
 syncFilterButtons();
 publish();
})();
""",
    "utf-8",
)


def patch_library_media_state_provider_response(
    target: str,
    response: ApiResponse,
    *,
    registry: WebModuleRegistry | None = None,
) -> ApiResponse:
    """Retire generic media tabs, then append the Library-owned state projection."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response

    body = response.body.replace(
        _NAVIGATION_MEDIA_FILTER_TABS,
        _NAVIGATION_NON_LIBRARY_TABS,
    )
    library_composed = registry is None or "library.catalog" in registry.as_mapping()
    if library_composed and _LIBRARY_MEDIA_STATE_PROVIDER_PATCH not in body:
        body += _LIBRARY_MEDIA_STATE_PROVIDER_PATCH

    if body == response.body:
        return response
    return ApiResponse(
        response.status,
        body,
        response.content_type,
        response.headers,
    )
