"""Final managed-browser cleanup for WEB-040 visible-control auditing.

This seam runs after the feature/workspace patches. It removes legacy controls that
remain visible but no longer own an action contract in the final desktop-aligned UI
and tags the surviving final-DOM action owners for durable browser auditing.
Workspace-specific action expansion remains in WEB-041 through WEB-046.
"""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_VISIBLE_CONTROL_AUDIT_PATCH = bytes(
    r"""

/* WEB-040: a visible control must have a real action contract. */
(()=>{
 if(window.__fieldoraVisibleControlAuditWired)return;
 window.__fieldoraVisibleControlAuditWired=true;

 /* The original Knowledge shell shipped two anonymous pseudo-tabs (Review queue /
    Accepted knowledge). The desktop-aligned workflow now owns navigation through
    Review knowledge / Add identification, while proposal state and explicit
    Accept/Reject/Defer actions are rendered by the governed Knowledge seam. Leaving
    the old pair visible creates two buttons with no event/action contract. */
 const legacyKnowledgeTabs=document.querySelector("#knowledge-review-panel > section.card > .tabs");
 if(legacyKnowledgeTabs)legacyKnowledgeTabs.remove();

 /* Keep the inventory attached to the final composed DOM. Most shipped controls own
    a direct onclick handler. The remaining selectors are deliberate delegated or
    addEventListener-owned controls introduced by later workspace patches. Dynamic
    controls are tagged when inserted so browser certification can fail closed on an
    unowned visible button instead of relying on a static HTML list. */
 const delegatedSelectors=[
  "button[data-page]",
  "button[data-home-target]",
  "button[data-workspace-target]",
  "button[data-library-view]",
  "button[data-import-source]",
  "button[data-media-filter]",
  "button[data-observation-filter]",
  "button[data-observation-decision]",
  "button[data-task-view]",
  "button[data-knowledge-review]",
  "button[data-research-domain]",
  "button[data-portfolio-view]",
  "button[data-operations-domain]",
  "button[data-op][data-service]",
  "button[data-unlink-evidence]",
  "button[data-approve]",
  "button[data-contract]",
  "button[data-collection-action]",
  "button[data-collection-id]",
 ];
 const listenerOwnedIds=new Set([
  "obs-save-aligned",
  "obs-cancel-aligned",
  "obs-supporting-link",
  "portfolio-new-project",
  "portfolio-project-save",
  "portfolio-project-cancel",
  "operator-refresh",
  "submission-create",
  "review-create",
  "review-determine",
  "review-accept",
 ]);
 function actionContract(button){
  if(typeof button.onclick==="function")return "direct-handler";
  if(listenerOwnedIds.has(button.id))return `listener:${button.id}`;
  const selector=delegatedSelectors.find(value=>button.matches(value));
  return selector?`delegated:${selector}`:"";
 }
 function tagButton(button){
  const contract=actionContract(button);
  if(contract)button.dataset.fieldoraActionContract=contract;
  else delete button.dataset.fieldoraActionContract;
 }
 function tagTree(root){
  if(root instanceof HTMLButtonElement)tagButton(root);
  root.querySelectorAll?.("button").forEach(tagButton);
 }
 tagTree(document);
 const observer=new MutationObserver(records=>records.forEach(record=>
  record.addedNodes.forEach(node=>{if(node instanceof Element)tagTree(node)})
 ));
 observer.observe(document.body,{childList:true,subtree:true});
 window.__fieldoraAuditVisibleButtons=()=>[...document.querySelectorAll("button")]
  .filter(button=>button.getClientRects().length>0&&!button.hidden)
  .map(button=>({
   id:button.id||"",
   text:(button.textContent||"").trim(),
   contract:button.dataset.fieldoraActionContract||"",
  }));
})();
""",
    "utf-8",
)


def patch_visible_control_audit_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _VISIBLE_CONTROL_AUDIT_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _VISIBLE_CONTROL_AUDIT_PATCH,
        response.content_type,
        response.headers,
    )
