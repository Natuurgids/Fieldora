"""Consistent workspace language for the managed Fieldora web client."""

from natureai_next.server.api import ApiResponse

_WORKSPACE_LANGUAGE_PATCH = bytes(
    r"""

/* Fieldora workspace language alignment: visible search/action wording must
   describe the current workspace after information-architecture restructuring. */
(()=>{
 if(window.__fieldoraWorkspaceLanguageWired)return;
 window.__fieldoraWorkspaceLanguageWired=true;
 const setSearch=(page,placeholder,label)=>{
  const host=document.getElementById(`page-${page}`);
  const input=host?.querySelector("input.search");
  if(!input)return;
  input.placeholder=placeholder;
  input.setAttribute("aria-label",label);
 };
 setSearch("home","Search Fieldora","Search Fieldora");
 setSearch("library","Search evidence","Search governed evidence");
 setSearch("observations","Search observations","Search observations");
 setSearch("research","Search research records","Search research records");
 setSearch("knowledge","Search knowledge","Search knowledge and analyses");

 const libraryImport=document.querySelector("#page-library .go-import");
 if(libraryImport)libraryImport.setAttribute("aria-label","Import evidence");
 const homeImport=document.querySelector("#page-home .go-import");
 if(homeImport)homeImport.setAttribute("aria-label","Import evidence");
})();
""",
    "utf-8",
)


def patch_workspace_language_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _WORKSPACE_LANGUAGE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _WORKSPACE_LANGUAGE_PATCH,
        response.content_type,
        response.headers,
    )
