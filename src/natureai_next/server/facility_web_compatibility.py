"""Browser enhancement for the shared Facilities Planning workflow."""
from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_FACILITY_PLANNING_SERVICE_PROVIDER_PATCH = bytes(
    r"""

/* WEB-FACILITIES-PLANNING-SERVICE: Facilities-owned planning transport. */
(()=>{
 if(window.__fieldoraFacilitiesPlanningServiceProviderWired)return;window.__fieldoraFacilitiesPlanningServiceProviderWired=true;
 const moduleId="facilities",contractName="facilities.planning.service",prefix="/api/v1/facility-planning";
 const encode=value=>encodeURIComponent(String(value??""));
 const request=(path,options={})=>api(`${prefix}${path}`,{purpose:"operations",...options});
 const post=(path,payload)=>request(path,{method:"POST",body:JSON.stringify(payload)});
 const implementation=Object.freeze({
  drawings:()=>request("/drawings"),
  plans:()=>request("/plans"),
  campaigns:()=>request("/campaigns"),
  campaign:id=>request(`/campaigns/${encode(id)}`),
  step:id=>request(`/steps/${encode(id)}`),
  addGeometry:(drawingId,payload)=>post(`/drawings/${encode(drawingId)}/geometries`,payload),
  createPlan:payload=>post("/plans",payload),
  addPlacement:(planId,payload)=>post(`/plans/${encode(planId)}/placements`,payload),
  createCampaign:payload=>post("/campaigns",payload),
  transitionStep:(stepId,state)=>post(`/steps/${encode(stepId)}/state`,{state})
 });
 function register(){
  const contracts=window.FieldoraModuleContracts;if(!contracts)return false;
  if(contracts.provider(contractName)!==moduleId)return false;
  const current=contracts.resolve(contractName);if(current)return current===implementation;
  contracts.register(contractName,moduleId,implementation);return true;
 }
 register();document.addEventListener("fieldora:contracts-ready",register,{once:true});
})();
""",
    "utf-8",
)

_FACILITY_WEB_PATCH = br"""

/* Fieldora Facilities Planning browser workspace. */
(()=>{
 const q=id=>document.getElementById(id),page=q("page-operations");if(!page||q("facility-planning-web"))return;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const section=document.createElement("section");section.id="facility-planning-web";section.className="card section";
 section.innerHTML=`<h2>Facilities Planning &amp; Relocation</h2><p class="muted">Current physical placement remains authoritative. Future layouts are proposals until a final relocation step explicitly confirms placement.</p><div class="grid"><section><h3>Versioned drawings</h3><div id="facility-drawings" class="list"></div><div class="form-grid"><label>Drawing ID<input id="facility-drawing-id"></label><label>Location ID<input id="facility-geometry-location"></label></div><label>Geometry JSON<textarea id="facility-geometry-json">{"x":0.5,"y":0.5}</textarea></label><button id="facility-add-geometry">Map location on drawing</button></section><section><h3>Future layouts</h3><div id="facility-plans" class="list"></div><div class="form-grid"><label>Name<input id="facility-plan-name"></label><label>Drawing ID<input id="facility-plan-drawing"></label><label>Version<input id="facility-plan-version"></label></div><button id="facility-plan-create">Create future layout</button><details class="section"><summary>Plan asset placement</summary><div class="form-grid"><label>Plan ID<input id="facility-placement-plan"></label><label>Asset ID<input id="facility-placement-asset"></label><label>Target location ID<input id="facility-placement-location"></label><label>Target geometry ID<input id="facility-placement-geometry"></label></div><button id="facility-placement-create">Plan placement</button></details></section><section><h3>Relocation campaigns</h3><div id="facility-campaigns" class="list"></div><div class="form-grid"><label>Name<input id="facility-campaign-name"></label><label>Plan ID<input id="facility-campaign-plan"></label></div><button id="facility-campaign-create">Create campaign</button></section></div><section class="section"><h3>Campaign execution</h3><label>Campaign ID<input id="facility-campaign-id"></label><button id="facility-campaign-open">Open campaign</button><div id="facility-campaign-detail" class="list section"></div></section><p id="facility-planning-status" class="status"></p>`;page.appendChild(section);
 function planningService(){return window.FieldoraModuleContracts?.resolve("facilities.planning.service")||null}
 async function loadAll(){try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");const [d,p,c]=await Promise.all([service.drawings(),service.plans(),service.campaigns()]);q("facility-drawings").innerHTML=(d.items||[]).map(x=>`<button class="row fp-drawing" data-id="${esc(x.id)}"><strong>${esc(x.title)}</strong><span>${esc(x.version||"")}</span><span>${esc(x.status||"")}</span><span>${esc(x.location_name||"")}</span></button>`).join("")||'<div class="empty">No drawings.</div>';q("facility-plans").innerHTML=(p.items||[]).map(x=>`<button class="row fp-plan" data-id="${esc(x.id)}"><strong>${esc(x.name)}</strong><span>${esc(x.version||"")}</span><span>${esc(x.status)}</span><span>${esc(x.id)}</span></button>`).join("")||'<div class="empty">No future layouts.</div>';q("facility-campaigns").innerHTML=(c.items||[]).map(x=>`<button class="row fp-campaign" data-id="${esc(x.id)}"><strong>${esc(x.name)}</strong><span>${esc(x.status)}</span><span>${esc(x.id)}</span></button>`).join("")||'<div class="empty">No campaigns.</div>';document.querySelectorAll(".fp-drawing").forEach(b=>b.onclick=()=>{q("facility-drawing-id").value=b.dataset.id;q("facility-plan-drawing").value=b.dataset.id});document.querySelectorAll(".fp-plan").forEach(b=>b.onclick=()=>{q("facility-placement-plan").value=b.dataset.id;q("facility-campaign-plan").value=b.dataset.id});document.querySelectorAll(".fp-campaign").forEach(b=>b.onclick=()=>{q("facility-campaign-id").value=b.dataset.id;openCampaign(b.dataset.id)});q("facility-planning-status").textContent="Facilities planning loaded."}catch(e){q("facility-planning-status").textContent=e.message}}
 async function openCampaign(id){if(!id)return;try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");const x=await service.campaign(id),steps=x.campaign?.steps||[];q("facility-campaign-detail").innerHTML=steps.map(s=>`<div class="row"><strong>${esc(s.asset_code||s.resource_id)} ${esc(s.asset_name||"")}</strong><span>${esc(s.from_name||s.from_code||"")} -&gt; ${esc(s.to_name||s.to_code||"")}</span><span class="pill">${esc(s.state)}</span><span>${["removed","in_transit","staging","stored","placed","displayed","completed"].map(state=>`<button data-step="${esc(s.id)}" data-state="${state}">${state.replaceAll("_"," ")}</button>`).join(" ")}</span></div>`).join("")||'<div class="empty">No move steps.</div>';document.querySelectorAll("#facility-campaign-detail [data-step]").forEach(b=>b.onclick=async()=>{try{await service.transitionStep(b.dataset.step,b.dataset.state);openCampaign(id);loadAll()}catch(e){q("facility-planning-status").textContent=e.message}})}catch(e){q("facility-planning-status").textContent=e.message}}
 q("facility-add-geometry").onclick=async()=>{try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");await service.addGeometry(q("facility-drawing-id").value.trim(),{location_id:q("facility-geometry-location").value.trim(),geometry_type:"point",geometry:JSON.parse(q("facility-geometry-json").value)});loadAll()}catch(e){q("facility-planning-status").textContent=e.message}};
 q("facility-plan-create").onclick=async()=>{try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");const x=await service.createPlan({name:q("facility-plan-name").value,drawing_id:q("facility-plan-drawing").value,version:q("facility-plan-version").value});q("facility-placement-plan").value=x.plan.id;q("facility-campaign-plan").value=x.plan.id;loadAll()}catch(e){q("facility-planning-status").textContent=e.message}};
 q("facility-placement-create").onclick=async()=>{try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");const id=q("facility-placement-plan").value.trim();await service.addPlacement(id,{asset_id:q("facility-placement-asset").value.trim(),target_location_id:q("facility-placement-location").value.trim(),target_geometry_id:q("facility-placement-geometry").value.trim()});q("facility-planning-status").textContent="Future placement saved; current location unchanged.";loadAll()}catch(e){q("facility-planning-status").textContent=e.message}};
 q("facility-campaign-create").onclick=async()=>{try{const service=planningService();if(!service)throw new Error("Facilities planning service is unavailable.");const x=await service.createCampaign({name:q("facility-campaign-name").value,plan_id:q("facility-campaign-plan").value});q("facility-campaign-id").value=x.campaign.id;loadAll();openCampaign(x.campaign.id)}catch(e){q("facility-planning-status").textContent=e.message}};
 q("facility-campaign-open").onclick=()=>openCampaign(q("facility-campaign-id").value.trim());
 function bindWorkspaceRefresh(){const host=window.FieldoraModuleContracts?.resolve("operations.workspace.host");if(!host||!planningService())return false;host.subscribe(()=>void loadAll());return true}
 if(!bindWorkspaceRefresh())document.addEventListener("fieldora:contracts-ready",bindWorkspaceRefresh,{once:true});
})();
"""


def patch_facility_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _FACILITY_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _FACILITY_PLANNING_SERVICE_PROVIDER_PATCH + _FACILITY_WEB_PATCH,
        response.content_type,
        response.headers,
    )
