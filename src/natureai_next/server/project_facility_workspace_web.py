"""Desktop-density Facility workspace for the managed Fieldora web client.

The Project cockpit is owned by Projects/Core. This adapter now owns only the
Facility/CMDB desktop-density workspace and consumes Operations through the
public ``operations.workspace.host`` contract.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_FACILITY_WORKSPACE_PATCH = bytes(
    r"""

/* Fieldora facility cockpit: desktop-density web workspace. */
(()=>{
 if(window.__fieldoraFacilityCockpit)return;
 window.__fieldoraFacilityCockpit=true;
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
  .cockpit-content{flex:1;overflow:auto;padding:8px}.cockpit-content .card{border-radius:7px}.cockpit-content>.card{border:0;background:transparent;padding:0}.cockpit-content .row{cursor:pointer;border-radius:4px}
  .inspector-tabs{display:flex;gap:4px;position:sticky;top:0;z-index:5;padding:7px;background:#152023;border-bottom:1px solid var(--line)}.inspector-panel{padding:10px}.inspector-panel[hidden]{display:none!important}.inspector-panel pre{white-space:pre-wrap;overflow-wrap:anywhere}.inspector-panel>.card{border:0;background:transparent;padding:0}
  .facility-kinds{display:flex;gap:5px;overflow:auto}.facility-kinds button{white-space:nowrap}.facility-record-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px}.facility-record-grid .row{display:block;border:1px solid var(--line);background:#172427}.facility-record-grid .row>*{display:block;margin:4px 0}
  .facility-map-stage{min-height:270px;border:1px dashed #46605b;border-radius:7px;background:linear-gradient(45deg,#132024 25%,#162529 25%,#162529 50%,#132024 50%,#132024 75%,#162529 75%);background-size:24px 24px;padding:12px}.facility-map-stage h3{margin-top:0}.facility-map-stage .muted{max-width:600px}
  @media(max-width:1180px){.desktop-cockpit{grid-template-columns:210px minmax(430px,1fr) 290px}.main{padding-left:14px;padding-right:14px}}
  @media(max-width:900px){.desktop-cockpit{display:block;height:auto;min-height:0}.cockpit-pane{max-height:none;overflow:visible}.cockpit-pane+.cockpit-pane{border-left:0;border-top:1px solid var(--line)}.cockpit-left{max-height:260px;overflow:auto}.cockpit-center{min-height:540px}.cockpit-right{min-height:360px}}
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

 const facilityPage=q("page-operations");
 let facilityView="assets";
 let facilityWorkspaceHost=null;
 let facilitySelectedRecordId="";
 function facilityHost(){return facilityWorkspaceHost||window.FieldoraModuleContracts?.resolve("operations.workspace.host")||null}
 function facilityRecords(){return facilityHost()?.records?.()||[]}
 function facilityFilter(items){
  if(facilityView==="buildings")return items.filter(x=>/building|site|campus/i.test(String(x.location_type||x.category||x.type||"")));
  if(facilityView==="rooms")return items.filter(x=>/room|lab|laboratory|floor|zone/i.test(String(x.location_type||x.category||x.type||"")));
  if(facilityView==="materials")return items.filter(x=>/material|consumable|stock|reagent|sample|equipment|instrument|asset/i.test(String(x.category||x.asset_type||x.type||"asset")));
  return items;
 }
 function facilityRecord(id){return facilityRecords().find(item=>String(item.id)===String(id))||null}
 function renderFacilityInspector(record){
  const props=q("facility-inspector-properties"),metadata=q("facility-inspector-metadata");
  if(!record){if(props)props.innerHTML='<div class="empty">Select a facility or CMDB record.</div>';if(metadata)metadata.innerHTML='<div class="empty">Select a facility or CMDB record.</div>';return}
  if(props)props.innerHTML=`<h3>${esc2(record.name||record.title||record.asset_code||record.code||record.id)}</h3><p><strong>Type</strong> ${esc2(record.category||record.location_type||record.maintenance_type||record.type||"—")}</p><p><strong>Status</strong> ${esc2(record.status||"—")}</p><p class="muted">${esc2(record.description||record.notes||"No description recorded.")}</p>`;
  if(metadata)metadata.innerHTML=`<h3>${esc2(record.name||record.title||record.id)}</h3><pre>${esc2(JSON.stringify(record,null,2))}</pre>`;
 }
 function selectFacilityRecord(id){
  facilitySelectedRecordId=String(id||"");
  renderFacilityTree();renderFacilityCenter(false);renderFacilityInspector(facilityRecord(facilitySelectedRecordId));
 }
 function renderFacilityTree(){
  const host=q("facility-cockpit-tree");if(!host)return;const all=facilityRecords(),items=facilityFilter(all),needle=(q("facility-tree-filter")?.value||"").toLowerCase();
  host.innerHTML=`<div class="tree-group"><div class="tree-label">Current view</div>${items.filter(x=>JSON.stringify(x).toLowerCase().includes(needle)).map(x=>`<button type="button" class="tree-item" data-facility-record="${esc2(x.id)}" aria-selected="${String(x.id)===facilitySelectedRecordId}"><span class="tree-icon">${facilityView==="drawings"?"⌑":facilityView==="assets"||facilityView==="materials"?"◆":"⌂"}</span><span>${esc2(x.name||x.title||x.asset_code||x.code||x.id)}</span></button>`).join("")||'<div class="empty">No records in this view.</div>'}</div>`;
  host.querySelectorAll("[data-facility-record]").forEach(b=>b.onclick=()=>selectFacilityRecord(b.dataset.facilityRecord));
 }
 function renderFacilityCenter(renderTree=true){
  const list=q("facility-workspace-records");if(!list)return;const all=facilityRecords(),items=facilityFilter(all);
  list.innerHTML=`<div class="facility-record-grid">${items.map(r=>`<button class="row" data-facility-record-row="${esc2(r.id)}" aria-selected="${String(r.id)===facilitySelectedRecordId}"><strong>${esc2(r.name||r.title||r.asset_code||r.code||r.id)}</strong><span>${esc2(r.category||r.location_type||r.maintenance_type||r.status||"")}</span><span>${esc2(r.description||r.notes||"")}</span></button>`).join("")||'<div class="empty">No records in this facility view.</div>'}</div>`;
  list.querySelectorAll("[data-facility-record-row]").forEach(b=>b.onclick=()=>selectFacilityRecord(b.dataset.facilityRecordRow));
  if(renderTree)renderFacilityTree();
 }
 async function setFacilityView(view){
  facilityView=view;facilitySelectedRecordId="";const domain=({buildings:"locations",rooms:"locations",assets:"assets",materials:"assets",drawings:"drawings",maintenance:"maintenance",calibrations:"calibrations"})[view]||"assets";
  document.querySelectorAll("[data-facility-view]").forEach(b=>b.classList.toggle("primary",b.dataset.facilityView===view));
  const host=facilityHost();if(!host)throw new Error("Facilities requires operations.workspace.host");
  await host.selectDomain(domain);
  renderFacilityInspector(null);
  const planning=q("facility-planning-web");if(planning)planning.hidden=view!=="drawings";
  const map=q("facility-inspector-map");if(map)map.innerHTML=view==="drawings"?'<div class="facility-map-stage"><h3>Building maps & floorplans</h3><p class="muted">Use versioned drawings, mapped room/location geometries, future layouts and relocation campaigns. Current placement remains authoritative until a governed relocation step completes.</p></div>':'<div class="facility-map-stage"><h3>Spatial context</h3><p class="muted">Choose Building maps & floorplans to manage versioned building drawings and location geometry.</p></div>';
 }
 if(facilityPage&&!q("facility-desktop-cockpit")){
  const shell=document.createElement("section");shell.id="facility-desktop-cockpit";shell.className="desktop-cockpit";
  const left=document.createElement("aside");left.className="cockpit-pane cockpit-left";left.innerHTML='<div class="cockpit-pane-head"><strong>Facilities</strong></div><div style="padding:7px"><input id="facility-tree-filter" placeholder="Filter facility / CMDB"></div><div class="cockpit-tree"><div class="tree-group"><div class="tree-label">Hierarchy</div><button class="tree-item" data-facility-view="buildings"><span class="tree-icon">▤</span>Buildings</button><button class="tree-item" data-facility-view="rooms"><span class="tree-icon">⌂</span>Floors, rooms & labs</button><button class="tree-item" data-facility-view="assets"><span class="tree-icon">◆</span>Equipment & assets</button><button class="tree-item" data-facility-view="materials"><span class="tree-icon">▦</span>Materials / CMDB</button><button class="tree-item" data-facility-view="drawings"><span class="tree-icon">⌑</span>Building maps & floorplans</button></div></div><div id="facility-cockpit-tree" class="cockpit-tree"></div>';
  const center=document.createElement("section");center.className="cockpit-pane cockpit-center";center.innerHTML='<div class="cockpit-pane-head"><strong>Facility management</strong><span class="muted" style="margin-left:auto">current state + planned layouts</span></div><div class="cockpit-toolbar facility-kinds"><button data-facility-view="buildings">Buildings</button><button data-facility-view="rooms">Rooms & Labs</button><button data-facility-view="assets" class="primary">Equipment</button><button data-facility-view="materials">Materials / CMDB</button><button data-facility-view="drawings">Maps & Floorplans</button><button data-facility-view="maintenance">Maintenance</button><button data-facility-view="calibrations">Calibration</button></div><div id="facility-workspace-records" class="cockpit-content"></div><div id="facility-workspace-planning" class="cockpit-content"></div>';
  const right=document.createElement("aside");right.className="cockpit-pane cockpit-right";
  const props=document.createElement("div");props.id="facility-inspector-properties";props.innerHTML='<div class="empty">Select a facility or CMDB record.</div>';
  const metadata=document.createElement("div");metadata.id="facility-inspector-metadata";metadata.className="muted";metadata.textContent="Select a facility or CMDB record.";const map=document.createElement("div");map.id="facility-inspector-map";const activity=document.createElement("div");activity.id="facility-inspector-activity";activity.innerHTML='<p class="muted">Maintenance, calibration and relocation state remain available as governed operational records.</p>';
  inspector(right,"facility-inspector",[["properties","Properties",props],["metadata","Metadata",metadata],["map","Map",map],["activity","Activity",activity]]);
  shell.append(left,center,right);const subnav=facilityPage.querySelector(".workspace-subnav");(subnav||facilityPage.querySelector(".top"))?.after(shell);
  const planning=q("facility-planning-web");if(planning){q("facility-workspace-planning").appendChild(planning);planning.hidden=true}
  q("facility-tree-filter").oninput=renderFacilityTree;document.querySelectorAll("[data-facility-view]").forEach(b=>b.onclick=()=>setFacilityView(b.dataset.facilityView));
  const bindFacilityWorkspace=()=>{
   const host=window.FieldoraModuleContracts?.resolve("operations.workspace.host");if(!host)return false;
   if(facilityWorkspaceHost===host)return true;
   facilityWorkspaceHost=host;host.subscribe(()=>renderFacilityCenter());void setFacilityView(facilityView);return true;
  };
  if(!bindFacilityWorkspace())document.addEventListener("fieldora:contracts-ready",bindFacilityWorkspace,{once:true});
 }
})();
""",
    "utf-8",
)


def patch_project_facility_workspace_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Append the desktop-density Facility workspace once to app.js."""
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
