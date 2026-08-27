"""Managed-browser Research record lifecycle for WEB-042."""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_RESEARCH_RECORDS_PATCH = bytes(
    r"""

/* WEB-042: Research records use server-owned identity and revisions. */
(()=>{
 if(window.__fieldoraResearchRecordsWired)return;
 window.__fieldoraResearchRecordsWired=true;
 const byId=id=>document.getElementById(id);
 const html=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
 let governedResearchRecords=[],editingResearchRecord=null;
 const list=byId("research-domain-list"),save=byId("science-save"),recordsCard=list?.closest(".card");
 if(!list||!save||!recordsCard)return;

 let detail=byId("research-record-detail");
 if(!detail){detail=document.createElement("div");detail.id="research-record-detail";detail.className="card section";detail.hidden=true;recordsCard.appendChild(detail)}
 function render(){
  list.innerHTML=governedResearchRecords.length?governedResearchRecords.map(item=>`<button type="button" class="row" data-research-record="${html(item.id)}"><strong>${html(item.name||item.id)}</strong><span>${html(item.project_id||"")}</span><span>${html(item.status||"")}</span><span>rev ${html(item.revision||1)}</span></button>`).join(""):'<div class="empty">No research records.</div>';
 }
 loadResearchDomain=async function(){
  try{
   const project=byId("science-project")?.value||selectedProject||"";
   const suffix=project?`?project_id=${encodeURIComponent(project)}`:"";
   governedResearchRecords=(await api(`/api/v1/${researchDomain}${suffix}`)).items||[];render();
  }catch(error){list.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 };
 function clearEditor(){editingResearchRecord=null;for(const id of ["science-name","science-parent","science-description"]){if(byId(id))byId(id).value=""}if(byId("science-status"))byId("science-status").value="active";save.textContent="Save research record";status("science-save-status","")}
 async function openRecord(id){
  try{
   const payload=await api(`/api/v1/${researchDomain}/${encodeURIComponent(id)}`),item=payload.item;
   editingResearchRecord={...item,revision:payload.revision||item.revision||1};
   if(byId("science-project")){byId("science-project").value=item.project_id||"";byId("science-project").disabled=true}
   byId("science-name").value=item.name||"";byId("science-status").value=item.status||"active";byId("science-parent").value=item.parent_id||"";byId("science-description").value=item.description||"";
   save.textContent="Update research record";
   detail.hidden=false;detail.innerHTML=`<h3>${html(item.name||item.id)}</h3><p><strong>${html(item.record_type||researchDomain)}</strong> · revision ${html(editingResearchRecord.revision)}</p><p>${html(item.description||"No description")}</p><p class="muted">Public ID <code>${html(item.id)}</code></p>`;
   recordsCard.querySelector("details")?.setAttribute("open","");
  }catch(error){status("science-save-status",error.message,true)}
 }
 list.onclick=event=>{const row=event.target.closest("[data-research-record]");if(row)openRecord(row.dataset.researchRecord)};
 async function saveRecord(){
  const project=byId("science-project")?.value||"",name=byId("science-name")?.value.trim()||"";
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
 save.onclick=saveRecord;
 byId("science-project")?.addEventListener("change",()=>{if(!editingResearchRecord)loadResearchDomain()});
 document.querySelectorAll("[data-research-domain]").forEach(button=>button.addEventListener("click",()=>{editingResearchRecord=null;if(byId("science-project"))byId("science-project").disabled=false;detail.hidden=true;clearEditor()}));
})();
""",
    "utf-8",
)


def patch_research_records_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _RESEARCH_RECORDS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _RESEARCH_RECORDS_PATCH,
        response.content_type,
        response.headers,
    )
