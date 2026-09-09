"""Library-owned media state provider for the managed web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import WebModuleRegistry

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
 const syncFilterButtons=()=>document.querySelectorAll("[data-media-filter]").forEach(button=>button.classList.toggle("primary",String(button.dataset.mediaFilter||"all")===filter));
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
    """Append the Library state owner after all compatibility projections."""

    if registry is not None and "library.catalog" not in registry.as_mapping():
        return response
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _LIBRARY_MEDIA_STATE_PROVIDER_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LIBRARY_MEDIA_STATE_PROVIDER_PATCH,
        response.content_type,
        response.headers,
    )
