"""Browser enhancement for the shared Facilities Planning workflow."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_FACILITY_WEB_PATCH = b"""
\n/* Fieldora Facilities Planning browser workspace. */
(()=>{
  const qf=id=>document.getElementById(id);
  const ef=value=>String(value??\"\").replace(/[&<>\"']/g,c=>({\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#39;\"}[c]));
  const page=qf(\"page-operations\");
  if(!page||qf(\"facility-planning-web\"))return;
  const section=document.createElement(\"section\");
  section.id=\"facility-planning-web\";section.className=\"card section\";
  section.innerHTML=`<h2>Facilities Planning &amp; Relocation</h2><p class=\"muted\">Current physical placement remains authoritative. Future layouts are proposals until a final relocation step explicitly confirms placement.</p><div class=\"grid\"><section><h3>Versioned drawings</h3><div id=\"facility-drawings\" class=\"list\"></div><label>Drawing ID<input id=\"facility-drawing-id\"></label><label>Location ID<input id=\"facility-geometry-location\"></label><label>Geometry JSON<textarea id=\"facility-geometry-json\">{\"x\":0.5,\"y\":0.5}</textarea></label><button id=\"facility-add-geometry\">Map location on drawing</button></section><section><h3>Future layouts</h3><div id=\"facility-plans\" class=\"list\"></div><div class=\"form-grid\"><label>Name<input id=\"facility-plan-name\"></label><label>Drawing ID<input id=\"facility-plan-drawing\"></label><label>Version<input id=\"facility-plan-version\"></label></div><button id=\"facility-plan-create\">Create future layout</button><details class=\"section\"><summary>Plan asset placement</summary><div class=\"form-grid\"><label>Plan ID<input id=\"facility-placement-plan\"></label><label>Asset ID<input id=\"facility-placement-asset\"></label><label>Target location ID<input id=\"facility-placement-location\"></label><label>Target geometry ID<input id=\"facility-placement-geometry\"></label></div><button id=\"facility-placement-create\">Plan placement</button></details></section><section><h3>Relocation campaigns</h3><div id=\"facility-campaigns\" class=\"list\"></div><div class=\"form-grid\"><label>Name<input id=\"facility-campaign-name\"></label><label>Plan ID<input id=\"facility-campaign-plan\"></label></div><button id=\"facility-campaign-create\">Create campaign</button></section></div><section class=\"section\"><h3>Campaign execution</h3><label>Campaign ID<input id=\"facility-campaign-id\"></label><button id=\"facility-campaign-open\">Open campaign</button><div id=\"facility-campaign-detail\" class=\"list section\"></div></section><p id=\"facility-planning-status\" class=\"status\"></p>`;
  page.appendChild(section);

  async function loadFacilitiesPlanning(){
    try{
      const [drawings,plans,campaigns]=await Promise.all([
        api(\"/api/v1/facility-planning/drawings\",{purpose:\"operations\"}),
        api(\"/api/v1/facility-planning/plans\",{purpose:\"operations\"}),
        api(\"/api/v1/facility-planning/campaigns\",{purpose:\"operations\"})
      ]);
      qf(\"facility-drawings\").innerHTML=(drawings.items||[]).map(x=>`<button class=\"row facility-drawing-row\" data-id=\"${ef(x.id)}\"><strong>${ef(x.title)}</strong><span>${ef(x.version||\"\")}</span><span>${ef(x.status||\"\")}</span><span>${ef(x.location_name||x.location_code||\"\")}</span></button>`).join(\"\")||'<div class=\"empty\">No drawings.</div>';
      qf(\"facility-plans\").innerHTML=(plans.items||[]).map(x=>`<button class=\"row facility-plan-row\" data-id=\"${ef(x.id)}\"><strong>${ef(x.name)}</strong><span>${ef(x.version||\"\")}</span><span>${ef(x.status)}</span><span>${ef(x.effective_at||\"\")}</span></button>`).join(\"\")||'<div class=\"empty\">No future layouts.</div>';
      qf(\"facility-campaigns\").innerHTML=(campaigns.items||[]).map(x=>`<button class=\"row facility-campaign-row\" data-id=\"${ef(x.id)}\"><strong>${ef(x.name)}</strong><span>${ef(x.status)}</span><span>${ef(x.scheduled_start||\"\")}</span><span>${ef(x.id)}</span></button>`).join(\"\")||'<div class=\"empty\">No relocation campaigns.</div>';
      document.querySelectorAll(\".facility-drawing-row\").forEach(b=>b.onclick=()=>{qf(\"facility-drawing-id\").value=b.dataset.id;qf(\"facility-plan-drawing\").value=b.dataset.id});
      document.querySelectorAll(\".facility-plan-row\").forEach(b=>b.onclick=()=>{qf(\"facility-placement-plan\").value=b.dataset.id;qf(\"facility-campaign-plan\").value=b.dataset.id});
      document.querySelectorAll(\".facility-campaign-row\").forEach(b=>b.onclick=()=>{qf(\"facility-campaign-id\").value=b.dataset.id;openCampaign(b.dataset.id)});
      qf(\"facility-planning-status\").textContent=\"Facilities planning loaded.\";
    }catch(e){qf(\"facility-planning-status\").textContent=e.message}
  }

  async function openCampaign(id){
    if(!id)return;
    try{
      const result=await api(`/api/v1/facility-planning/campaigns/${encodeURIComponent(id)}`,{purpose:\"operations\"});
      const steps=result.campaign?.steps||[];
      qf(\"facility-campaign-detail\").innerHTML=steps.map(s=>`<div class=\"row\"><strong>${ef(s.asset_code||s.resource_id)} · ${ef(s.asset_name||\"\")}</strong><span>${ef(s.from_name||s.from_code||\"\")} → ${ef(s.to_name||s.to_code||\"\")}</span><span class=\"pill\">${ef(s.state)}</span><span>${[\"removed\",\"in_transit\",\"staging\",\"stored\",\"placed\",\"displayed\",\"completed\"].map(state=>`<button data-step=\"${ef(s.id)}\" data-state=\"${state}\">${state.replaceAll(\"_\",\" \")}</button>`).join(\" \")}</span></div>`).join(\"\")||'<div class=\"empty\">Campaign contains no move steps.</div>';
      document.querySelectorAll(\"#facility-campaign-detail [data-step]\").forEach(button=>button.onclick=async()=>{try{await api(`/api/v1/facility-planning/steps/${button.dataset.step}/state`,{method:\"POST\",purpose:\"operations\",body:JSON.stringify({state:button.dataset.state})});openCampaign(id);loadFacilitiesPlanning()}catch(e){qf(\"facility-planning-status\").textContent=e.message}});
    }catch(e){qf(\"facility-planning-status\").textContent=e.message}
  }

  qf(\"facility-add-geometry\").onclick=async()=>{try{await api(`/api/v1/facility-planning/drawings/${encodeURIComponent(qf(\"facility-drawing-id\").value.trim())}/geometries`,{method:\"POST\",purpose:\"operations\",body:JSON.stringify({location_id:qf(\"facility-geometry-location\").value.trim(),geometry_type:\"point\",geometry:JSON.parse(qf(\"facility-geometry-json\").value)})});loadFacilitiesPlanning()}catch(e){qf(\"facility-planning-status\").textContent=e.message}};
  qf(\"facility-plan-create\").onclick=async()=>{try{const result=await api(\"/api/v1/facility-planning/plans\",{method:\"POST\",purpose:\"operations\",body:JSON.stringify({name:qf(\"facility-plan-name\").value,drawing_id:qf(\"facility-plan-drawing\").value,version:qf(\"facility-plan-version\").value})});qf(\"facility-placement-plan\").value=result.plan.id;qf(\"facility-campaign-plan\").value=result.plan.id;loadFacilitiesPlanning()}catch(e){qf(\"facility-planning-status\").textContent=e.message}};
  qf(\"facility-placement-create\").onclick=async()=>{try{const plan=qf(\"facility-placement-plan\").value.trim();await api(`/api/v1/facility-planning/plans/${encodeURIComponent(plan)}/placements`,{method:\"POST\",purpose:\"operations\",body:JSON.stringify({asset_id:qf(\"facility-placement-asset\").value.trim(),target_location_id:qf(\"facility-placement-location\").value.trim(),target_geometry_id:qf(\"facility-placement-geometry\").value.trim()})});qf(\"facility-planning-status\").textContent=\"Future placement saved; current physical location unchanged.\";loadFacilitiesPlanning()}catch(e){qf(\"facility-planning-status\").textContent=e.message}};
  qf(\"facility-campaign-create\").onclick=async()=>{try{const result=await api(\"/api/v1/facility-planning/campaigns\",{method:\"POST\",purpose:\"operations\",body:JSON.stringify({name:qf(\"facility-campaign-name\").value,plan_id:qf(\"facility-campaign-plan\").value})});qf(\"facility-campaign-id\").value=result.campaign.id;loadFacilitiesPlanning();openCampaign(result.campaign.id)}catch(e){qf(\"facility-planning-status\").textContent=e.message}};
  qf(\"facility-campaign-open\").onclick=()=>openCampaign(qf(\"facility-campaign-id\").value.trim());

  document.querySelectorAll('.nav[data-page=\"operations\"]').forEach(button=>button.addEventListener(\"click\",loadFacilitiesPlanning));
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
        response.body + _FACILITY_WEB_PATCH,
        response.content_type,
        response.headers,
    )
