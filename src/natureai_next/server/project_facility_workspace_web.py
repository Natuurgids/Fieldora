"""Desktop-density project and facility workspaces for the managed web client.

This enhancement deliberately reuses the established server controls and API calls.
It rearranges existing governed controls instead of creating a second client-side data
model, so PBAC, audit, uploads, portfolio actions, CMDB records, drawings and relocation
planning keep their existing server semantics.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_FACILITY_WORKSPACE_PATCH = bytes(
    r"""

/* Fieldora project + facility cockpit: desktop-density web workspace. */
(()=>{
 if(window.__fieldoraProjectFacilityCockpit)return;
 window.__fieldoraProjectFacilityCockpit=true;
 const q=id=>document.getElementById(id);
 const esc2=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const style=document.createElement("style");
 style.textContent=`
  .cockpit-page .top{margin-bottom:8px}.cockpit-page>.workspace-subnav{margin-bottom:8px}
  .desktop-cockpit{display:grid;grid-template-columns:minmax(205px,18%) minmax(480px,1fr) minmax(280px,25%);height:calc(100vh - 150px);min-height:590px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#111a1d}
  .cockpit-pane{min-width:0;min-height:0;background:var(--panel);overflow:auto}.cockpit-pane+.cockpit-pane{border-left:1px solid var(--line)}
  .cockpit-pane-head{position:sticky;top:0;z-index:4;display:flex;gap:7px;align-items:center;min-height:45px;padding:7px 9px;background:#152023;border-bottom:1px solid var(--line)}
  .cockpit-pane-head strong{white-space:nowrap}.cockpit-pane-head input{width:100%;min-width:0;padding:7px 9px}
  .cockpit-tree{padding:5px}.tree-group{margin:5px 0 9px}.tree-label{padding:7px 8px;color:var(--muted);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
  .tree-item{width:100%;display:flex;gap:7px;align-items:center;border:0;border-radius:5px;background:transparent;text-align:left;padding:7px 8px;color:#d7e3df}.tree-item:hover,.tree-item[aria-selected="true"]{background:#203b32;color:#fff}.tree-item .tree-icon{width:18px;text-align:center;color:var(--green)}
  .cockpit-center{display:flex;flex-direction:column;overflow:hidden}.cockpit-toolbar{display:flex;gap:7px;align-items:center;flex-wrap:wrap;padding:7px 9px;border-bottom:1px solid var(--line);background:#182326}.cockpit-toolbar .tabs{margin:0}.cockpit-toolbar button,.inspector-tabs button{padding:6px 9px;border-radius:5px;background:transparent}.cockpit-toolbar button.primary,.inspector-tabs button[aria-selected="true"]{background:#254239;border-color:#4f8e6a;color:#fff}
  .cockpit-content{flex:1;overflow:auto;padding:8px}.cockpit-content .card{border-radius:7px}.cockpit-content>.card{border:0;background:transparent;padding:0}.cockpit-content .row{cursor:pointer;border-radius:4px}.cockpit-content .portfolio-project{background:#18282a}
  .portfolio-kanban{display:grid;grid-template-columns:repeat(4,minmax(190px,1fr));gap:8px;min-width:800px}.portfolio-column{background:#121d20;border:1px solid var(--line);border-radius:7px;padding:7px}.portfolio-column h3{font-size:13px;color:var(--muted);text-transform:uppercase}.portfolio-ticket{display:block;width:100%;text-align:left;margin:6px 0;padding:9px;background:#1c292d;border:1px solid #334448;border-radius:6px}.portfolio-ticket small{display:block;color:var(--muted);margin-top:5px}
  .portfolio-grid-view{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}.portfolio-grid-view .row{display:block;border:1px solid var(--line);background:#172427}.portfolio-grid-view .row>*{display:block;margin:4px 0}
  .portfolio-summary-table{width:100%;border-collapse:collapse}.portfolio-summary-table th,.portfolio-summary-table td{text-align:left;padding:9px;border-bottom:1px solid var(--line)}
  .inspector-tabs{display:flex;gap:4px;position:sticky;top:0;z-index:5;padding:7px;background:#152023;border-bottom:1px solid var(--line)}.inspector-panel{padding:10px}.inspector-panel[hidden]{display:none!important}.inspector-panel pre{white-space:pre-wrap;overflow-wrap:anywhere}.inspector-panel>.card{border:0;background:transparent;padding:0}
  .project-evidence-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}.project-evidence{min-height:120px;padding:9px;border:1px solid var(--line);border-radius:6px;background:#172427}.project-evidence strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.project-evidence .thumb{height:75px}
  .facility-kinds{display:flex;gap:5px;overflow:auto}.facility-kinds button{white-space:nowrap}.facility-record-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px}.facility-record-grid .row{display:block;border:1px solid var(--line);background:#172427}.facility-record-grid .row>*{display:block;margin:4px 0}
  .facility-map-stage{min-height:270px;border:1px dashed #46605b;border-radius:7px;background:linear-gradient(45deg,#132024 25%,#162529 25%,#162529 50%,#132024 50%,#132024 75%,#162529 75%);background-size:24px 24px;padding:12px}.facility-map-stage h3{margin-top:0}.facility-map-stage .muted{max-width:600px}
  .cockpit-editor details>summary{cursor:pointer;font-weight:600}.cockpit-editor .form-grid{grid-template-columns:1fr}.cockpit-editor textarea{min-height:120px}
  @media(max-width:1180px){.desktop-cockpit{grid-template-columns:210px minmax(430px,1fr) 290px}.main{padding-left:14px;padding-right:14px}}
  @media(max-width:900px){.desktop-cockpit{display:block;height:auto;min-height:0}.cockpit-pane{max-height:none;overflow:visible}.cockpit-pane+.cockpit-pane{border-left:0;border-top:1px solid var(--line)}.cockpit-left{max-height:260px;overflow:auto}.cockpit-center{min-height:540px}.cockpit-right{min-height:360px}.portfolio-kanban{overflow:auto}}
 `;
 document.head.appendChild(style);

 function inspector(host,prefix,tabs){
  const bar=document.createElement("div");bar.className="inspector-tabs";
  tabs.forEach(([key,label,node])=>{
   const b=document.createElement("button");b.type="button";b.dataset.inspector=key;b.textContent=label;b.onclick=()=>selectInspector(host,prefix,key);bar.appendChild(b);
   const panel=document.createElement("section");panel.id=`${prefix}-${key}`;panel.className="inspector-panel";if(node)panel.appendChild(node);host.appendChild(panel);
  });
  host.prepend(bar);selectInspector(host,prefix,tabs[0][0]);
 }
 function selectInspector(host,prefix,key){
  host.querySelectorAll(".inspector-tabs [data-inspector]").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.inspector===key)));
  host.querySelectorAll(`.inspector-panel[id^="${prefix}-"]`).forEach(p=>p.hidden=p.id!==`${prefix}-${key}`);
 }

 /* ---- Project cockpit -------------------------------------------------- */
 const projectPage=q("page-projects");
 let cockpitProjectId="";
 let projectEvidence=[];
 function projectById(id){return (projects||[]).find(p=>p.id===id)||null}
 function renderProjectTree(){
  const host=q("project-cockpit-tree");if(!host)return;
  const needle=(q("project-tree-filter")?.value||"").toLowerCase();
  const visible=(projects||[]).filter(p=>JSON.stringify(p).toLowerCase().includes(needle));
  host.innerHTML=`<div class="tree-group"><div class="tree-label">Projects</div>${visible.map(p=>`<button type="button" class="tree-item" data-project-tree="${esc2(p.id)}" aria-selected="${p.id===cockpitProjectId}"><span class="tree-icon">▦</span><span>${esc2(p.name||p.title||p.id)}</span></button>`).join("")||'<div class="empty">No accessible projects.</div>'}</div><div class="tree-group"><div class="tree-label">Saved views</div><button type="button" class="tree-item" data-project-scope="mine"><span class="tree-icon">★</span>My work</button><button type="button" class="tree-item" data-project-scope="all"><span class="tree-icon">≡</span>All accessible</button></div>`;
  host.querySelectorAll("[data-project-tree]").forEach(b=>b.onclick=()=>selectCockpitProject(b.dataset.projectTree));
  host.querySelectorAll("[data-project-scope]").forEach(b=>b.onclick=()=>{q("portfolio-scope").value=b.dataset.projectScope;loadPortfolio()});
 }
 async function selectCockpitProject(id){
  cockpitProjectId=id||"";selectedProject=cockpitProjectId;
  if(q("work-project"))q("work-project").value=cockpitProjectId;
  renderProjectTree();renderProjectInspector(projectById(cockpitProjectId));
  try{const result=await api("/api/v1/media?limit=500");projectEvidence=(result.items||[]).filter(m=>m.project_id===cockpitProjectId);renderProjectEvidence()}catch(_e){projectEvidence=[];renderProjectEvidence()}
 }
 function renderProjectInspector(record){
  const properties=q("project-inspector-properties-content"),metadata=q("project-inspector-metadata"),map=q("project-inspector-map"),activity=q("project-inspector-activity");
  if(!record){if(metadata)metadata.innerHTML='<div class="empty">Select a project or work item.</div>';if(map)map.innerHTML='<div class="empty">Select a project to inspect its spatial context.</div>';if(activity)activity.innerHTML='<div class="empty">Select a record.</div>';return}
  if(metadata)metadata.innerHTML=`<h3>${esc2(record.name||record.title||record.id)}</h3><pre>${esc2(JSON.stringify(record,null,2))}</pre>`;
  if(map)map.innerHTML=`<div class="facility-map-stage"><h3>Project map</h3><p>${esc2(record.name||record.title||record.id)}</p><p class="muted">${esc2(record.research_area||record.location||record.geography||"No spatial boundary has been recorded for this project yet.")}</p><p class="muted">Map packages remain governed by the Fieldora map installation and offline-map services; this inspector uses the project spatial metadata already stored by the server.</p></div>`;
  if(activity)activity.innerHTML=`<h3>Record activity</h3><p><strong>Status</strong> ${esc2(record.status||"active")}</p><p><strong>Created</strong> ${esc2(record.created_at||record.created||"—")}</p><p><strong>Updated</strong> ${esc2(record.updated_at||record.modified_at||record.updated||"—")}</p><p class="muted">Authoritative security and change history remains in the governed audit log.</p>`;
  if(properties&&q("portfolio-detail")&&!properties.contains(q("portfolio-detail")))properties.appendChild(q("portfolio-detail"));
 }
 function renderProjectEvidence(){
  const host=q("project-workspace-evidence");if(!host)return;
  host.innerHTML=projectEvidence.length?`<div class="project-evidence-grid">${projectEvidence.map(m=>`<article class="project-evidence" data-media="${esc2(m.media_id)}"><div class="thumb">${String(m.mime_type||"").startsWith("image/")?"▧":String(m.mime_type||"").startsWith("audio/")?"≋":String(m.mime_type||"").startsWith("video/")?"▷":"▤"}</div><strong>${esc2(m.filename||m.name||m.media_id)}</strong><small class="muted">${esc2(m.mime_type||"")}</small></article>`).join("")}</div>`:'<div class="empty">No evidence is linked to the selected project.</div>';
 }
 function portfolioData(){return {tasks:JSON.parse(q("portfolio-list")?.dataset.tasks||"[]"),phases:JSON.parse(q("portfolio-list")?.dataset.phases||"[]"),sprints:JSON.parse(q("portfolio-list")?.dataset.sprints||"[]")}}
 function applyPortfolioView(){
  const list=q("portfolio-list");if(!list)return;const data=portfolioData(),tasks=cockpitProjectId?data.tasks.filter(t=>t.project_id===cockpitProjectId):data.tasks;
  if(portfolioView==="hierarchy")return;
  if(portfolioView==="kanban"){
   const statuses=["planned","active","blocked","done"];
   list.innerHTML=`<div class="portfolio-kanban">${statuses.map(state=>`<section class="portfolio-column"><h3>${state}</h3>${tasks.filter(t=>{const s=String(t.status||"active").toLowerCase();return state==="active"?["active","in_progress","started"].includes(s):state==="done"?["done","completed","closed"].includes(s):s===state}).map(t=>`<button class="portfolio-ticket" data-portfolio-id="${esc2(t.id)}" data-kind="task"><strong>${esc2(t.name||t.title||t.id)}</strong><small>${esc2(t.assignee_id||"Unassigned")} · ${esc2(t.manual_estimate||0)} h</small></button>`).join("")||'<p class="muted">No work</p>'}</section>`).join("")}</div>`;
  }else if(portfolioView==="grid"){
   list.innerHTML=`<div class="portfolio-grid-view">${tasks.map(t=>`<div class="row" data-portfolio-id="${esc2(t.id)}" data-kind="task"><strong>${esc2(t.name||t.title||t.id)}</strong><span>${esc2(t.assignee_id||"Unassigned")}</span><span class="pill">${esc2(t.status||"active")}</span></div>`).join("")||'<p class="empty">No work items.</p>'}</div>`;
  }else if(portfolioView==="gantt"){
   list.innerHTML=`<table class="portfolio-summary-table"><thead><tr><th>Work</th><th>Start</th><th>Due</th><th>Status</th></tr></thead><tbody>${tasks.map(t=>`<tr data-portfolio-id="${esc2(t.id)}" data-kind="task"><td>${esc2(t.name||t.title||t.id)}</td><td>${esc2(t.starts_at||t.start_date||"—")}</td><td>${esc2(t.ends_at||t.due_date||"—")}</td><td>${esc2(t.status||"active")}</td></tr>`).join("")}</tbody></table>`;
  }else if(portfolioView==="workload"){
   const by=new Map();tasks.forEach(t=>{const who=t.assignee_id||"Unassigned",x=by.get(who)||{estimate:0,realized:0,count:0};x.estimate+=Number(t.manual_estimate||0);x.realized+=Number(t.realized||0);x.count++;by.set(who,x)});list.innerHTML=`<table class="portfolio-summary-table"><thead><tr><th>Assignee</th><th>Items</th><th>Estimate</th><th>Realized</th></tr></thead><tbody>${[...by].map(([who,x])=>`<tr><td>${esc2(who)}</td><td>${x.count}</td><td>${x.estimate.toFixed(2)} h</td><td>${x.realized.toFixed(2)} h</td></tr>`).join("")}</tbody></table>`;
  }else if(portfolioView==="budget"){
   const rows=(cockpitProjectId?[projectById(cockpitProjectId)].filter(Boolean):(projects||[]));list.innerHTML=`<table class="portfolio-summary-table"><thead><tr><th>Project</th><th>Budget</th><th>Cost / realized</th><th>Status</th></tr></thead><tbody>${rows.map(p=>`<tr data-portfolio-id="${esc2(p.id)}" data-kind="project"><td>${esc2(p.name||p.title||p.id)}</td><td>${esc2(p.budget??p.budget_amount??"—")}</td><td>${esc2(p.cost??p.realized_cost??"—")}</td><td>${esc2(p.status||"active")}</td></tr>`).join("")}</tbody></table>`;
  }
 }
 function setProjectCenter(view){
  q("project-workspace-work").hidden=view!=="work";q("project-workspace-evidence").hidden=view!=="evidence";
  document.querySelectorAll("[data-project-center]").forEach(b=>b.classList.toggle("primary",b.dataset.projectCenter===view));
  if(view==="evidence"&&!projectEvidence.length&&cockpitProjectId)selectCockpitProject(cockpitProjectId);
 }
 if(projectPage&&!q("project-desktop-cockpit")){
  projectPage.classList.add("cockpit-page");
  const oldSplit=q("portfolio-list")?.closest(".split"),listCard=q("portfolio-list")?.closest(".card"),detailCard=q("portfolio-detail")?.closest(".card"),editor=q("work-save")?.closest(".card.section"),viewTabs=[...projectPage.children].find(n=>n.classList?.contains("tabs"));
  const shell=document.createElement("section");shell.id="project-desktop-cockpit";shell.className="desktop-cockpit";
  const left=document.createElement("aside");left.className="cockpit-pane cockpit-left";left.innerHTML='<div class="cockpit-pane-head"><strong>Projects</strong></div><div style="padding:7px"><input id="project-tree-filter" placeholder="Filter projects"></div><div id="project-cockpit-tree" class="cockpit-tree"></div>';
  const center=document.createElement("section");center.className="cockpit-pane cockpit-center";center.innerHTML='<div class="cockpit-pane-head"><strong id="project-cockpit-title">Project workspace</strong><span class="muted" style="margin-left:auto">governed server workspace</span></div><div class="cockpit-toolbar"><button type="button" class="primary" data-project-center="work">Work</button><button type="button" data-project-center="evidence">Evidence</button></div><div id="project-workspace-work" class="cockpit-content"></div><div id="project-workspace-evidence" class="cockpit-content" hidden></div>';
  const right=document.createElement("aside");right.className="cockpit-pane cockpit-right";
  const props=document.createElement("div");props.id="project-inspector-properties-content";if(detailCard)props.appendChild(detailCard);if(editor){const details=document.createElement("details");details.className="cockpit-editor section";details.innerHTML='<summary>Create / update work item</summary>';details.appendChild(editor);props.appendChild(details)}
  const metadata=document.createElement("div");metadata.id="project-inspector-metadata";metadata.className="muted";metadata.textContent="Select a project or work item.";
  const map=document.createElement("div");map.id="project-inspector-map";const activity=document.createElement("div");activity.id="project-inspector-activity";
  inspector(right,"project-inspector",[["properties","Properties",props],["metadata","Metadata",metadata],["map","Map",map],["activity","Activity",activity]]);
  shell.append(left,center,right);const subnav=projectPage.querySelector(".workspace-subnav");(subnav||projectPage.querySelector(".top"))?.after(shell);
  if(listCard)q("project-workspace-work").appendChild(listCard);if(viewTabs)center.querySelector(".cockpit-toolbar").appendChild(viewTabs);if(oldSplit)oldSplit.remove();
  q("project-tree-filter").oninput=renderProjectTree;center.querySelectorAll("[data-project-center]").forEach(b=>b.onclick=()=>setProjectCenter(b.dataset.projectCenter));
  const oldPortfolio=loadPortfolio;loadPortfolio=async function(){await oldPortfolio();renderProjectTree();applyPortfolioView();if(!cockpitProjectId&&projects?.length)selectCockpitProject(projects[0].id)};
  q("portfolio-list").addEventListener("click",e=>{const row=e.target.closest("[data-portfolio-id]");if(!row)return;const kind=row.dataset.kind,id=row.dataset.portfolioId,data=kind==="project"?projects:JSON.parse(q("portfolio-list").dataset[kind==="phase"?"phases":"tasks"]||"[]"),record=(data||[]).find(x=>x.id===id);if(kind==="project")cockpitProjectId=id;renderProjectInspector(record);selectInspector(right,"project-inspector","properties")},true);
  renderProjectTree();
 }

 /* ---- Facility / CMDB cockpit ----------------------------------------- */
 const facilityPage=q("page-operations");
 let facilityView="assets";
 function facilityFilter(items){
  if(facilityView==="buildings")return items.filter(x=>/building|site|campus/i.test(String(x.location_type||x.category||x.type||"")));
  if(facilityView==="rooms")return items.filter(x=>/room|lab|laboratory|floor|zone/i.test(String(x.location_type||x.category||x.type||"")));
  if(facilityView==="materials")return items.filter(x=>/material|consumable|stock|reagent|sample|equipment|instrument|asset/i.test(String(x.category||x.asset_type||x.type||"asset")));
  return items;
 }
 function renderFacilityTree(){
  const host=q("facility-cockpit-tree"),list=q("operations-list");if(!host||!list)return;const all=JSON.parse(list.dataset.records||"[]"),items=facilityFilter(all),needle=(q("facility-tree-filter")?.value||"").toLowerCase();
  host.innerHTML=`<div class="tree-group"><div class="tree-label">Current view</div>${items.filter(x=>JSON.stringify(x).toLowerCase().includes(needle)).map(x=>`<button type="button" class="tree-item" data-facility-record="${esc2(x.id)}"><span class="tree-icon">${facilityView==="drawings"?"⌑":facilityView==="assets"||facilityView==="materials"?"◆":"⌂"}</span><span>${esc2(x.name||x.title||x.asset_code||x.code||x.id)}</span></button>`).join("")||'<div class="empty">No records in this view.</div>'}</div>`;
  host.querySelectorAll("[data-facility-record]").forEach(b=>b.onclick=()=>{const row=list.querySelector(`[data-operations-id="${CSS.escape(b.dataset.facilityRecord)}"]`);row?.click()});
 }
 function renderFacilityCenter(){
  const list=q("operations-list");if(!list)return;const all=JSON.parse(list.dataset.records||"[]"),items=facilityFilter(all);
  list.innerHTML=`<div class="facility-record-grid">${items.map(r=>`<button class="row" data-operations-id="${esc2(r.id)}"><strong>${esc2(r.name||r.title||r.asset_code||r.code||r.id)}</strong><span>${esc2(r.category||r.location_type||r.maintenance_type||r.status||"")}</span><span>${esc2(r.description||r.notes||"")}</span></button>`).join("")||'<div class="empty">No records in this facility view.</div>'}</div>`;
  renderFacilityTree();
 }
 async function setFacilityView(view){
  facilityView=view;operationsDomain=({buildings:"locations",rooms:"locations",assets:"assets",materials:"assets",drawings:"drawings",maintenance:"maintenance",calibrations:"calibrations"})[view]||"assets";
  document.querySelectorAll("[data-facility-view]").forEach(b=>b.classList.toggle("primary",b.dataset.facilityView===view));
  await loadOperations();
  const planning=q("facility-planning-web");if(planning)planning.hidden=view!=="drawings";
  const map=q("facility-inspector-map");if(map)map.innerHTML=view==="drawings"?'<div class="facility-map-stage"><h3>Building maps & floorplans</h3><p class="muted">Use versioned drawings, mapped room/location geometries, future layouts and relocation campaigns. Current placement remains authoritative until a governed relocation step completes.</p></div>':'<div class="facility-map-stage"><h3>Spatial context</h3><p class="muted">Choose Building maps & floorplans to manage versioned building drawings and location geometry.</p></div>';
 }
 if(facilityPage&&!q("facility-desktop-cockpit")){
  facilityPage.classList.add("cockpit-page");
  const oldSplit=q("operations-list")?.closest(".split"),listCard=q("operations-list")?.closest(".card"),detailCard=q("operations-detail")?.closest(".card"),editor=q("operations-save")?.closest(".card.section"),legacyTabs=[...facilityPage.children].find(n=>n.classList?.contains("tabs"));
  if(legacyTabs)legacyTabs.hidden=true;
  const shell=document.createElement("section");shell.id="facility-desktop-cockpit";shell.className="desktop-cockpit";
  const left=document.createElement("aside");left.className="cockpit-pane cockpit-left";left.innerHTML='<div class="cockpit-pane-head"><strong>Facilities</strong></div><div style="padding:7px"><input id="facility-tree-filter" placeholder="Filter facility / CMDB"></div><div class="cockpit-tree"><div class="tree-group"><div class="tree-label">Hierarchy</div><button class="tree-item" data-facility-view="buildings"><span class="tree-icon">▤</span>Buildings</button><button class="tree-item" data-facility-view="rooms"><span class="tree-icon">⌂</span>Floors, rooms & labs</button><button class="tree-item" data-facility-view="assets"><span class="tree-icon">◆</span>Equipment & assets</button><button class="tree-item" data-facility-view="materials"><span class="tree-icon">▦</span>Materials / CMDB</button><button class="tree-item" data-facility-view="drawings"><span class="tree-icon">⌑</span>Building maps & floorplans</button></div></div><div id="facility-cockpit-tree" class="cockpit-tree"></div>';
  const center=document.createElement("section");center.className="cockpit-pane cockpit-center";center.innerHTML='<div class="cockpit-pane-head"><strong>Facility management</strong><span class="muted" style="margin-left:auto">current state + planned layouts</span></div><div class="cockpit-toolbar facility-kinds"><button data-facility-view="buildings">Buildings</button><button data-facility-view="rooms">Rooms & Labs</button><button data-facility-view="assets" class="primary">Equipment</button><button data-facility-view="materials">Materials / CMDB</button><button data-facility-view="drawings">Maps & Floorplans</button><button data-facility-view="maintenance">Maintenance</button><button data-facility-view="calibrations">Calibration</button></div><div id="facility-workspace-records" class="cockpit-content"></div><div id="facility-workspace-planning" class="cockpit-content"></div>';
  const right=document.createElement("aside");right.className="cockpit-pane cockpit-right";
  const props=document.createElement("div");if(detailCard)props.appendChild(detailCard);if(editor){const details=document.createElement("details");details.className="cockpit-editor section";details.open=false;details.innerHTML='<summary>Create / update facility or CMDB record</summary>';details.appendChild(editor);props.appendChild(details)}
  const metadata=document.createElement("div");metadata.id="facility-inspector-metadata";metadata.className="muted";metadata.textContent="Select a facility or CMDB record.";const map=document.createElement("div");map.id="facility-inspector-map";const activity=document.createElement("div");activity.id="facility-inspector-activity";activity.innerHTML='<p class="muted">Maintenance, calibration and relocation state remain available as governed operational records.</p>';
  inspector(right,"facility-inspector",[["properties","Properties",props],["metadata","Metadata",metadata],["map","Map",map],["activity","Activity",activity]]);
  shell.append(left,center,right);const subnav=facilityPage.querySelector(".workspace-subnav");(subnav||facilityPage.querySelector(".top"))?.after(shell);
  if(listCard)q("facility-workspace-records").appendChild(listCard);if(oldSplit)oldSplit.remove();
  const planning=q("facility-planning-web");if(planning){q("facility-workspace-planning").appendChild(planning);planning.hidden=true}
  q("facility-tree-filter").oninput=renderFacilityTree;document.querySelectorAll("[data-facility-view]").forEach(b=>b.onclick=()=>setFacilityView(b.dataset.facilityView));
  const oldOperations=loadOperations;loadOperations=async function(){await oldOperations();renderFacilityCenter()};
  q("operations-list").addEventListener("click",e=>{const row=e.target.closest("[data-operations-id]");if(!row)return;const items=JSON.parse(q("operations-list").dataset.records||"[]"),record=items.find(x=>x.id===row.dataset.operationsId);q("facility-inspector-metadata").innerHTML=record?`<h3>${esc2(record.name||record.title||record.id)}</h3><pre>${esc2(JSON.stringify(record,null,2))}</pre>`:'<div class="empty">Record unavailable.</div>';selectInspector(right,"facility-inspector","properties")},true);
  setFacilityView("assets");
 }
})();
""",
    "utf-8",
)


def patch_project_facility_workspace_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the desktop-density project/facility workspace once to app.js."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PROJECT_FACILITY_WORKSPACE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _PROJECT_FACILITY_WORKSPACE_PATCH,
        response.content_type,
        response.headers,
    )
