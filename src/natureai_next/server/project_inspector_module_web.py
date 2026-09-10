"""Replaceable Projects inspector consumer for selected-record state."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_INSPECTOR_MODULE_PATCH = bytes(
    r"""

/* WEB-PROJECT-INSPECTOR-MODULE: selected-record contract consumer. */
(()=>{
 if(window.__fieldoraProjectInspectorModuleWired)return;window.__fieldoraProjectInspectorModuleWired=true;
 const moduleId="projects.core",q=id=>document.getElementById(id);
 const selectedRecord=()=>window.FieldoraModuleContracts?.resolve?.("projects.selected-record.select")||null;
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 function ensureSurface(){
  const host=q("project-inspector-host")||q("project-desktop-cockpit")?.querySelector(".cockpit-right");if(!host)return null;
  if(q("project-inspector-metadata"))return host;
  const bar=document.createElement("div");bar.className="inspector-tabs";
  const panels=[
   ["properties","Properties"],
   ["metadata","Metadata"],
   ["map","Map"],
   ["activity","Activity"],
  ];
  panels.forEach(([key,label])=>{
   const button=document.createElement("button");button.type="button";button.dataset.inspector=key;button.textContent=label;button.addEventListener("click",()=>selectTab(key));bar.appendChild(button);
   const panel=document.createElement("section");panel.id=`project-inspector-${key}`;panel.className="inspector-panel";
   if(key==="properties"){
    const props=document.createElement("div");props.id="project-inspector-properties-content";panel.appendChild(props);
    const detail=q("portfolio-detail")?.closest(".card");if(detail&&!props.contains(detail))props.appendChild(detail);
    const editor=q("work-editor");if(editor){const details=document.createElement("details");details.className="cockpit-editor section";details.innerHTML='<summary>Create / update work item</summary>';details.appendChild(editor);props.appendChild(details)}
   }else if(key==="metadata")panel.innerHTML='<div class="muted">Select a project or work item.</div>';
   else if(key==="map")panel.innerHTML='<div class="empty">Select a project to inspect its spatial context.</div>';
   else panel.innerHTML='<div class="empty">Select a record.</div>';
   host.appendChild(panel);
  });
  host.prepend(bar);selectTab("properties");return host;
 }
 function selectTab(key){
  const host=ensureSurface();if(!host)return;
  host.querySelectorAll(".inspector-tabs [data-inspector]").forEach(button=>button.setAttribute("aria-selected",String(button.dataset.inspector===key)));
  host.querySelectorAll('.inspector-panel[id^="project-inspector-"]').forEach(panel=>panel.hidden=panel.id!==`project-inspector-${key}`);
 }
 function render(selection){
  ensureSurface();const record=selection?.record||null,metadata=q("project-inspector-metadata"),map=q("project-inspector-map"),activity=q("project-inspector-activity"),title=q("project-cockpit-title");
  if(title)title.textContent=record?.name||record?.title||"Project workspace";
  if(!record){if(metadata)metadata.innerHTML='<div class="empty">Select a project or work item.</div>';if(map)map.innerHTML='<div class="empty">Select a project to inspect its spatial context.</div>';if(activity)activity.innerHTML='<div class="empty">Select a record.</div>';return}
  if(metadata)metadata.innerHTML=`<h3>${esc(record.name||record.title||record.id)}</h3><pre>${esc(JSON.stringify(record,null,2))}</pre>`;
  if(map)map.innerHTML=`<div class="facility-map-stage"><h3>Project map</h3><p>${esc(record.name||record.title||record.id)}</p><p class="muted">${esc(record.research_area||record.location||record.geography||"No spatial boundary has been recorded for this project yet.")}</p><p class="muted">Map packages remain governed by Fieldora map installation and offline-map services.</p></div>`;
  if(activity)activity.innerHTML=`<h3>Record activity</h3><p><strong>Status</strong> ${esc(record.status||"active")}</p><p><strong>Created</strong> ${esc(record.created_at||record.created||"—")}</p><p><strong>Updated</strong> ${esc(record.updated_at||record.modified_at||record.updated||"—")}</p><p class="muted">Authoritative security and change history remains in the governed audit log.</p>`;
  selectTab("properties");
 }
 function refresh(){ensureSurface();render(selectedRecord()?.current?.()||null)}
 document.addEventListener("fieldora:project-selected-record-changed",event=>render(event.detail?.selection||null));
 document.addEventListener("fieldora:contract-registered",event=>{if(event.detail?.contract==="projects.selected-record.select")refresh()});
 document.addEventListener("fieldora:module-mount",event=>{if(event.detail?.module?.module_id===moduleId)refresh()});
 refresh();
})();
""",
    "utf-8",
)


def patch_project_inspector_module_response(target: str, response: ApiResponse) -> ApiResponse:
    """Append the inspector only when the selected-record provider is present."""

    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-PROJECT-SELECTED-RECORD-PROVIDER" not in response.body
        or _PROJECT_INSPECTOR_MODULE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_INSPECTOR_MODULE_PATCH,
        response.content_type,
        response.headers,
    )
