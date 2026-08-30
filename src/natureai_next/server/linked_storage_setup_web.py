"""Browser handoff from the Library linked-archive empty state to Operator setup."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LINKED_STORAGE_SETUP_WEB_PATCH = bytes(
    r"""

/* Fieldora linked archive setup handoff. */
(()=>{
 if(window.__fieldoraLinkedStorageSetupHandoffWired)return;
 window.__fieldoraLinkedStorageSetupHandoffWired=true;
 const byId=id=>document.getElementById(id);

 function wireSetupHandoff(){
  const card=byId("linked-storage-card"),operatorNav=document.querySelector('.nav[data-page="operator"]');
  if(!card||!operatorNav)return false;
  if(byId("linked-storage-operator-setup"))return true;
  const actions=document.createElement("div");actions.className="actions section";
  actions.innerHTML='<button id="linked-storage-operator-setup" type="button">Set up linked archive</button>';
  const status=byId("linked-storage-status");
  if(status)status.after(actions);else card.querySelector(".linked-toolbar")?.after(actions);
  byId("linked-storage-operator-setup").addEventListener("click",()=>{
   showPage("operator");
   setTimeout(()=>{
    const setup=byId("operator-linked-service-enroll")?.closest("section")||byId("operator-linked-archives")?.closest("section");
    setup?.scrollIntoView({behavior:"smooth",block:"start"});
    byId("operator-linked-service-name")?.focus();
   },0);
  });
  return true;
 }

 if(!wireSetupHandoff()){
  const observer=new MutationObserver(()=>{if(wireSetupHandoff())observer.disconnect()});
  observer.observe(document.body,{childList:true,subtree:true});
 }
})();
""",
    "utf-8",
)


def patch_linked_storage_setup_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the Library-to-Operator setup handoff to the managed app bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _LINKED_STORAGE_SETUP_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LINKED_STORAGE_SETUP_WEB_PATCH,
        response.content_type,
        response.headers,
    )
