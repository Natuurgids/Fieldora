"""Managed-browser Research record lifecycle for WEB-042."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_LEGACY_RESEARCH_SAVE_START = b"async function saveScienceRecord(){"
_LEGACY_RESEARCH_SAVE_END = b"async function reviewSelected(statusValue){"
_LEGACY_RESEARCH_SAVE_WIRING = b'q("science-save").onclick=saveScienceRecord;'

_RESEARCH_RECORDS_PATCH = bytes(
    r"""

/* WEB-042: Research records use server-owned identity and revisions. */
(()=>{
 if(window.__fieldoraResearchRecordsWired)return;
 window.__fieldoraResearchRecordsWired=true;
 const byId=id=>document.getElementById(id);
 const html=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
 const projectContext=()=>window.FieldoraModuleContracts?.resolve?.("projects.context.select")||null;
 let governedResearchRecords=[],editingResearchRecord=null,integrationProjectId="";
 const list=byId("research-domain-list"),save=byId("science-save"),recordsCard=list?.closest(".card");
 if(!list||!save||!recordsCard)return;

 let detail=byId("research-record-detail");
 if(!detail){detail=document.createElement("div");detail.id="research-record-detail";detail.className="card section";detail.hidden=true;recordsCard.appendChild(detail)}
 function render(){
  list.innerHTML=governedResearchRecords.length?governedResearchRecords.map(item=>`<button type="button" class="row" data-research-record="${html(item.id)}"><strong>${html(item.name||item.id)}</strong><span>${html(item.project_id||"")}</span><span>${html(item.status||"")}</span><span>rev ${html(item.revision||1)}</span></button>`).join(""):'<div class="empty">No research records.</div>';
 }
 loadResearchDomain=async function(){
  try{
   const project=integrationProjectId||byId("science-project")?.value||projectContext()?.current?.()||"";
   const suffix=project?`?project_id=${encodeURIComponent(project)}`:"";
   governedResearchRecords=(await api(`/api/v1/${researchDomain}${suffix}`)).items||[];render();
  }catch(error){list.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 };
 function clearEditor(){editingResearchRecord=null;for(const id of ["science-name","science-parent","science-description"]){if(byId(id))byId(id).value=""}if(byId("science-status"))byId("science-status").value="active";save.textContent="Save research record";status("science-save-status","")}
 async function openRecord(id){
  try{
   const payload=await api(`/api/v1/${researchDomain}/${encodeURIComponent(id)}`),item=payload.item;
   editingResearchRecord={...item,revision:payload.revision||item.revision||1};integrationProjectId=item.project_id||integrationProjectId;
   if(byId("science-project")){byId("science-project").value=item.project_id||"";byId("science-project").disabled=true}
   byId("science-name").value=item.name||"";byId("science-status").value=item.status||"active";byId("science-parent").value=item.parent_id||"";byId("science-description").value=item.description||"";
   save.textContent="Update research record";
   detail.hidden=false;detail.innerHTML=`<h3>${html(item.name||item.id)}</h3><p><strong>${html(item.record_type||researchDomain)}</strong> · revision ${html(editingResearchRecord.revision)}</p><p>${html(item.description||"No description")}</p><p class="muted">Public ID <code>${html(item.id)}</code></p>`;
   recordsCard.querySelector("details")?.setAttribute("open","");
  }catch(error){status("science-save-status",error.message,true)}
 }
 list.onclick=event=>{const row=event.target.closest("[data-research-record]");if(row)openRecord(row.dataset.researchRecord)};
 async function saveRecord(){
  const project=integrationProjectId||byId("science-project")?.value||"",name=byId("science-name")?.value.trim()||"";
  if(!project||!name)return status("science-save-status","Project and name are required.",true);
  const record={project_id:project,name,status:byId("science-status")?.value.trim()||"active",parent_id:byId("science-parent")?.value.trim()||"",description:byId("science-description")?.value.trim()||"",payload:{}};
  try{
   if(editingResearchRecord){
    const changes={name:record.name,status:record.status,parent_id:record.parent_id,description:record.description,payload:record.payload};
    const result=await api(`/api/v1/${researchDomain}/${encodeURIComponent(editingResearchRecord.id)}`,{method:"PATCH",headers:{"If-Match":String(editingResearchRecord.revision)},body:JSON.stringify(changes)});
    editingResearchRecord={...result.item,revision:result.revision};status("science-save-status","Research record updated.");
   }else{
    await api(`/api/v1/${researchDomain}`,{method:"POST",body:JSON.stringify(record)});status("science-save-status","Research record created.");
   }
   if(byId("science-project"))byId("science-project").disabled=false;clearEditor();detail.hidden=true;await loadResearchDomain();
  }catch(error){status("science-save-status",error.message,true)}
 }
 async function openProject(projectId){
  const project=String(projectId||"").trim();if(!project)return false;
  integrationProjectId=project;editingResearchRecord=null;
  const selector=byId("science-project");if(selector){selector.disabled=false;selector.value=project}
  detail.hidden=true;clearEditor();await loadResearchDomain();return true;
 }
 save.onclick=saveRecord;
 byId("science-project")?.addEventListener("change",()=>{if(!editingResearchRecord){integrationProjectId=byId("science-project")?.value||"";loadResearchDomain()}});
 document.querySelectorAll("[data-research-domain]").forEach(button=>button.addEventListener("click",()=>{editingResearchRecord=null;if(byId("science-project"))byId("science-project").disabled=false;detail.hidden=true;clearEditor()}));
 window.FieldoraResearchRecords=Object.freeze({openProject,refresh:()=>loadResearchDomain(),currentProject:()=>integrationProjectId||byId("science-project")?.value||""});
})();
""",
    "utf-8",
)


def _retire_legacy_research_save(body: bytes) -> bytes:
    start = body.find(_LEGACY_RESEARCH_SAVE_START)
    end = body.find(_LEGACY_RESEARCH_SAVE_END, start) if start >= 0 else -1
    if start >= 0 and end >= 0:
        body = body[:start] + body[end:]
    return body.replace(_LEGACY_RESEARCH_SAVE_WIRING, b"", 1)


def patch_research_records_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _RESEARCH_RECORDS_PATCH in response.body
    ):
        return response
    body = _retire_legacy_research_save(response.body)
    return ApiResponse(
        response.status,
        body + _RESEARCH_RECORDS_PATCH,
        response.content_type,
        response.headers,
    )
