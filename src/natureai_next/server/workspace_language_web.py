"""Consistent workspace language and scoped search for managed Fieldora web."""

from natureai_next.server.api import ApiResponse

_WORKSPACE_LANGUAGE_PATCH = bytes(
    r"""

/* Fieldora workspace language alignment: visible search/action wording must
   describe the current workspace after information-architecture restructuring.
   Do not expose search controls that have no behavior. */
(()=>{
 if(window.__fieldoraWorkspaceLanguageWired)return;
 window.__fieldoraWorkspaceLanguageWired=true;
 const style=document.createElement("style");
 style.textContent=`
  #research-domain-list .row[hidden]{display:none!important}
  #research-search-empty[hidden]{display:none!important}
 `;
 document.head.appendChild(style);
 const setSearch=(page,placeholder,label)=>{
  const host=document.getElementById(`page-${page}`);
  const input=host?.querySelector("input.search");
  if(!input)return null;
  input.placeholder=placeholder;
  input.setAttribute("aria-label",label);
  return input;
 };

 const homeSearch=setSearch("home","Search Fieldora","Search Fieldora");
 // Home is a launch surface. The inherited search box had no handler and was
 // therefore misleading, so keep it out of the task surface until a governed
 // cross-workspace search exists.
 if(homeSearch)homeSearch.hidden=true;

 setSearch("library","Search evidence","Search governed evidence");
 setSearch("observations","Search observations","Search observations");
 const researchSearch=setSearch(
  "research","Search research records","Search research records"
 );
 setSearch("knowledge","Search knowledge","Search knowledge and analyses");

 // Research inherited a generic search field but the base client never wired it.
 // Make it a deliberately local filter over the currently loaded record domain.
 const researchList=document.getElementById("research-domain-list");
 const noMatches=document.createElement("p");
 noMatches.id="research-search-empty";
 noMatches.className="empty";
 noMatches.textContent="No research records match this filter.";
 noMatches.hidden=true;
 researchList?.after(noMatches);
 const filterResearchRecords=()=>{
  if(!researchSearch||!researchList)return;
  const query=(researchSearch.value||"").trim().toLowerCase();
  const rows=[...researchList.querySelectorAll(".row")];
  let visible=0;
  rows.forEach(row=>{
   const matches=!query||row.innerText.toLowerCase().includes(query);
   row.hidden=!matches;
   if(matches)visible+=1;
  });
  noMatches.hidden=!query||rows.length===0||visible>0;
 };
 if(researchSearch){
  researchSearch.classList.remove("global-search");
  researchSearch.oninput=filterResearchRecords;
 }
 if(researchList){
  new MutationObserver(filterResearchRecords).observe(researchList,{childList:true});
  filterResearchRecords();
 }

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
