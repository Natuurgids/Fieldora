"""Keep Collections and Datasets with governed Library evidence in the web client."""

from natureai_next.server.api import ApiResponse

_LIBRARY_COLLECTIONS_PATCH = bytes(
    r"""

/* Fieldora Library alignment: Collections/Datasets belong with governed evidence,
   not in the Research-record surface. */
(()=>{
 if(window.__fieldoraLibraryCollectionsWired)return;
 window.__fieldoraLibraryCollectionsWired=true;
 const collections=document.getElementById("collection-list")?.closest(".card");
 const browse=document.getElementById("library-browse-panel");
 if(!collections||!browse)return;
 collections.id="library-collections-card";
 const heading=collections.querySelector("h2");
 if(heading)heading.textContent="Collections & Datasets";
 const intro=document.createElement("p");
 intro.className="muted";
 intro.textContent="Organize governed Library evidence without changing its provenance or source ownership.";
 if(heading)heading.after(intro);
 browse.appendChild(collections);
})();
""",
    "utf-8",
)


def patch_library_collections_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _LIBRARY_COLLECTIONS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LIBRARY_COLLECTIONS_PATCH,
        response.content_type,
        response.headers,
    )
