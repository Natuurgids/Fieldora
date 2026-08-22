"""Compatibility surface for the Fieldora managed-server web client.

Web and Qt need not be pixel-identical, but evidence ownership, scientific concepts,
service lifecycle, and principal workflows must remain recognizable across clients.
This module provides public operations/docs aliases and a narrow browser enhancement
layer while the static reference client remains dependency-free.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next import __version__
from natureai_next.server.api import ApiResponse

_HEALTH_ALIASES = {
    "/health": "/api/v1/health/ready",
    "/health/live": "/api/v1/health/live",
    "/health/ready": "/api/v1/health/ready",
}

# This is appended to the existing application bundle. It intentionally corrects
# domain/workflow assumptions without forking a second browser application.
_WEB_PLATFORM_PATCH = b"""
\n/* Fieldora Platform compatibility: Library-first intake, review, and operations. */
(()=>{
  const fq=id=>document.getElementById(id);
  const fesc=value=>String(value??\"\").replace(/[&<>\"']/g,c=>({\"&\":\"&amp;\",\"<\":\"&lt;\",\">\":\"&gt;\",'\"':\"&quot;\",\"'\":\"&#39;\"}[c]));

  const previousProjectOptions=projectOptions;
  projectOptions=function(){
    previousProjectOptions();
    const select=fq(\"upload-project\");
    if(select){
      const first=select.querySelector('option[value=\"\"]');
      if(first)first.textContent=\"General Library (no project)\";
      const label=select.closest(\"label\");
      if(label&&label.firstChild)label.firstChild.textContent=\"Project (optional)\";
    }
  };

  const projectSelect=fq(\"upload-project\");
  if(projectSelect){
    const first=projectSelect.querySelector('option[value=\"\"]');
    if(first)first.textContent=\"General Library (no project)\";
    const label=projectSelect.closest(\"label\");
    if(label&&label.firstChild)label.firstChild.textContent=\"Project (optional)\";
  }
  const stageProject=fq(\"stage-project\");
  if(stageProject){
    stageProject.placeholder=\"Leave empty for General Library\";
    const label=stageProject.closest(\"label\");
    if(label&&label.firstChild)label.firstChild.textContent=\"Project ID (optional)\";
  }

  async function governedUpload(){
    const file=fq(\"upload-file\")?.files?.[0];
    const project=fq(\"upload-project\")?.value||\"\";
    if(!file)return status(\"upload-status\",\"Choose a file. Project is optional.\",true);
    status(\"upload-status\",\"Calculating SHA-256…\");
    const bytes=await file.arrayBuffer();
    const digest=await crypto.subtle.digest(\"SHA-256\",bytes);
    const hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,\"0\")).join(\"\");
    try{
      const begun=await api(\"/api/v1/uploads\",{method:\"POST\",body:JSON.stringify({project_id:project,filename:file.name,mime_type:file.type,size_bytes:file.size,sha256:hash})});
      const chunk=4*1024*1024;
      let result=null;
      for(let start=0;start<file.size;start+=chunk){
        const end=Math.min(file.size,start+chunk);
        result=await api(`/api/v1/uploads/${begun.upload_id}`,{method:\"PUT\",headers:{\"Content-Range\":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});
        status(\"upload-status\",`Uploaded ${Math.round(end/file.size*100)}%`);
      }
      status(\"upload-status\",`Upload verified · ${project?\"project-linked\":\"General Library\"} · media ${result?.media_id||\"\"}`);
      loadMedia();
    }catch(e){status(\"upload-status\",e.message,true)}
  }

  async function governedStagedUpload(){
    const files=[...(fq(\"stage-files\")?.files||[])];
    const project=fq(\"stage-project\")?.value?.trim()||\"\";
    if(!files.length)return status(\"stage-status\",\"Choose one or more files. Project is optional.\",true);
    try{
      let submission=await api(\"/api/v1/staged-submissions\",{method:\"POST\",body:JSON.stringify({project_id:project,contract_id:fq(\"stage-contract\")?.value||\"\",publication_policy:fq(\"stage-policy\")?.value||\"review\",expected_files:files.length})});
      const sid=submission.submission.submission_id;
      for(const file of files){
        const bytes=await file.arrayBuffer();
        const hash=[...new Uint8Array(await crypto.subtle.digest(\"SHA-256\",bytes))].map(x=>x.toString(16).padStart(2,\"0\")).join(\"\");
        const begun=await api(`/api/v1/staged-submissions/${sid}/files`,{method:\"POST\",body:JSON.stringify({filename:file.name,relative_path:file.webkitRelativePath||file.name,mime_type:file.type,size_bytes:file.size,sha256:hash})});
        for(let start=0;start<file.size;start+=4*1024*1024){
          const end=Math.min(file.size,start+4*1024*1024);
          await api(`/api/v1/staged-files/${begun.staged_file_id}`,{method:\"PUT\",headers:{\"Content-Range\":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});
        }
      }
      await api(`/api/v1/staged-submissions/${sid}/seal`,{method:\"POST\",body:\"{}\"});
      const processed=await api(`/api/v1/staged-submissions/${sid}/process`,{method:\"POST\",body:\"{}\"});
      status(\"stage-status\",`Submission ${sid} · ${project?\"project context\":\"General Library\"} · ${processed.submission?.state||\"queued\"}`);
    }catch(e){status(\"stage-status\",e.message,true)}
  }

  function replaceAction(id,handler){
    const old=fq(id);if(!old)return;
    const fresh=old.cloneNode(true);old.replaceWith(fresh);fresh.onclick=handler;
  }
  replaceAction(\"upload-start\",governedUpload);
  replaceAction(\"stage-start\",governedStagedUpload);

  document.querySelectorAll(\".go-import\").forEach(button=>button.onclick=()=>{
    showPage(\"library\");
    const card=fq(\"import-card\");if(card)card.scrollIntoView({behavior:\"smooth\",block:\"start\"});
    const picker=fq(\"upload-file\");if(picker){picker.focus();picker.click();}
  });

  const previousRenderMedia=renderMedia;
  renderMedia=function(){
    previousRenderMedia();
    document.querySelectorAll(\"#media-grid article[data-media]\").forEach(card=>{
      const id=card.dataset.media,record=media.find(item=>item.media_id===id);
      if(!record||record.project_id)return;
      const note=card.querySelector(\"p.muted\");
      if(note)note.textContent=`${(record.size_bytes/1048576).toFixed(2)} MB · General Library`;
    });
  };

  function addPlatformPage(name,icon,title,html,loader){
    const nav=document.querySelector(\".sidebar nav\"),main=document.querySelector(\"main.main\");
    if(!nav||!main||fq(`page-${name}`))return;
    const button=document.createElement(\"button\");
    button.className=\"nav\";button.dataset.page=name;
    button.innerHTML=`<span class=\"nav-icon\">${icon}</span>${fesc(title)}`;
    button.onclick=()=>{showPage(name);loader()};nav.appendChild(button);
    const page=document.createElement(\"section\");
    page.className=\"page\";page.id=`page-${name}`;page.hidden=true;page.innerHTML=html;main.appendChild(page);
  }

  async function loadIntakeReview(){
    try{
      const [submissions,reviews]=await Promise.all([api(\"/api/v1/submissions?limit=100\"),api(\"/api/v1/review-cases?limit=100\")]);
      const s=fq(\"platform-submissions\");if(s)s.innerHTML=(submissions.items||[]).map(x=>`<div class=\"row\"><strong>${fesc(x.source_type)}</strong><span>${fesc(x.project_id||\"General Library\")}</span><span>${fesc(x.collection_id||x.state)}</span><span>${fesc(x.submission_id)}</span></div>`).join(\"\")||'<div class=\"empty\">No submissions.</div>';
      const r=fq(\"platform-reviews\");if(r)r.innerHTML=(reviews.items||[]).map(x=>`<button class=\"row platform-review\" data-case=\"${fesc(x.review_case_id)}\"><strong>${fesc(x.domain)}</strong><span>${fesc(x.specialty||\"General\")}</span><span>${fesc(x.state)}</span><span>${fesc(x.subject_id)}</span></button>`).join(\"\")||'<div class=\"empty\">No review cases.</div>';
      document.querySelectorAll(\".platform-review\").forEach(button=>button.onclick=()=>{fq(\"review-case-id\").value=button.dataset.case;loadReviewDetail(button.dataset.case)});
    }catch(e){const s=fq(\"intake-review-status\");if(s)s.textContent=e.message}
  }

  async function loadReviewDetail(id){
    if(!id)return;
    try{
      const result=await api(`/api/v1/review-cases/${encodeURIComponent(id)}`);
      const node=fq(\"review-detail\");
      if(node)node.innerHTML=`<p><strong>${fesc(result.review_case.domain)}</strong> · ${fesc(result.review_case.specialty||\"general\")} · ${fesc(result.review_case.state)}</p>`+(result.determinations||[]).map(d=>`<div class=\"row\"><strong>${fesc(d.assertion)}</strong><span>${Math.round(Number(d.confidence)*100)}%</span><span>${fesc(d.expert_id)}</span><span>${fesc(d.determination_id)}</span></div>`).join(\"\");
    }catch(e){fq(\"review-detail\").textContent=e.message}
  }

  addPlatformPage(\"intake-review\",\"◇\",\"Intake & Review\",`<div class=\"top\"><h1>Intake &amp; Expert Review</h1></div><p class=\"muted\">Evidence may enter the governed Library without belonging to a project. Review cases route evidence to appropriate expert domains while preserving every determination.</p><div class=\"grid\"><section class=\"card\"><h2>Register submission</h2><div class=\"form-grid\"><label>Source type<input id=\"submission-source\" value=\"external-contributor\"></label><label>Source reference<input id=\"submission-reference\"></label><label>Project ID (optional)<input id=\"submission-project\"></label><label>Collection ID (optional)<input id=\"submission-collection\"></label><label>License / rights<input id=\"submission-license\"></label><label>Consent code<input id=\"submission-consent\"></label></div><button id=\"submission-create\" class=\"primary section\">Register submission</button></section><section class=\"card\"><h2>Request expert review</h2><div class=\"form-grid\"><label>Subject type<input id=\"review-subject-type\" value=\"asset\"></label><label>Subject ID<input id=\"review-subject\"></label><label>Project ID (optional)<input id=\"review-project\"></label><label>Expert domain<input id=\"review-domain\" placeholder=\"taxonomy, pathology, geology…\"></label><label>Specialty<input id=\"review-specialty\"></label><label>Geography<input id=\"review-geography\"></label></div><button id=\"review-create\" class=\"primary section\">Request review</button></section></div><section class=\"card section\"><h2>Submissions</h2><div id=\"platform-submissions\" class=\"list\"></div></section><section class=\"card section\"><h2>Expert review queue</h2><div id=\"platform-reviews\" class=\"list\"></div></section><section class=\"card section\"><h2>Review determination</h2><div class=\"form-grid\"><label>Review case ID<input id=\"review-case-id\"></label><label>Assertion<input id=\"review-assertion\"></label><label>Confidence 0–1<input id=\"review-confidence\" type=\"number\" min=\"0\" max=\"1\" step=\".01\" value=\"0.8\"></label><label>Accept determination ID<input id=\"review-accept-id\"></label></div><div class=\"actions section\"><button id=\"review-determine\" class=\"primary\">Add determination</button><button id=\"review-accept\">Accept determination</button></div><div id=\"review-detail\" class=\"section\"></div></section><p id=\"intake-review-status\" class=\"status\"></p>`,loadIntakeReview);

  async function loadOperator(){
    const target=fq(\"operator-overview\");
    try{
      const data=await api(\"/api/v1/operator/overview\",{purpose:\"administration\"});
      const counts=data.service_counts||{};
      fq(\"operator-metrics\").innerHTML=[[\"Active services\",counts.active||0],[\"Draining\",counts.draining||0],[\"Stale\",data.stale_service_count||0],[\"Certificates expiring\",data.expiring_certificate_count||0]].map(([a,b])=>`<section class=\"card metric\"><span class=\"muted\">${fesc(a)}</span><strong>${fesc(b)}</strong></section>`).join(\"\");
      target.innerHTML=(data.services||[]).map(s=>`<div class=\"row\"><strong>${fesc(s.name)}</strong><span>${fesc(s.service_type)} · ${fesc(s.node_name)}</span><span class=\"pill\">${fesc(s.state)}</span><span><button data-service-op=\"drain\" data-service=\"${fesc(s.service_id)}\">Drain</button> <button data-service-op=\"activate\" data-service=\"${fesc(s.service_id)}\">Activate</button> <button data-service-op=\"stop\" data-service=\"${fesc(s.service_id)}\">Stop</button> <button class=\"danger\" data-service-op=\"revoke\" data-service=\"${fesc(s.service_id)}\">Revoke</button></span></div>`).join(\"\")||'<div class=\"empty\">No enrolled services yet.</div>';
      fq(\"operator-storage\").innerHTML=(data.storage||[]).map(s=>`<div class=\"row\"><strong>${fesc(s.path)}</strong><span>${(s.used_bytes/1073741824).toFixed(2)} GiB used</span><span>${(s.free_bytes/1073741824).toFixed(2)} GiB free</span><span>${fesc(s.used_percent)}%</span></div>`).join(\"\")||'<div class=\"empty\">No managed filesystem capacity reported.</div>';
      fq(\"operator-jobs\").textContent=JSON.stringify(data.jobs||{},null,2);
      fq(\"operator-runtime\").textContent=JSON.stringify(data.runtime||{},null,2);
      document.querySelectorAll(\"[data-service-op]\").forEach(button=>button.onclick=async()=>{try{await api(`/api/v1/operator/services/${button.dataset.service}/${button.dataset.serviceOp}`,{method:\"POST\",purpose:\"administration\",body:\"{}\"});loadOperator()}catch(e){fq(\"operator-status\").textContent=e.message}});
    }catch(e){target.textContent=e.message}
  }

  addPlatformPage(\"operator\",\"◉\",\"Operator\",`<div class=\"top\"><h1>Fieldora Operator</h1><button id=\"operator-refresh\">Refresh</button></div><p class=\"muted\">Durable enrolled services, capacity, queues, certificates and lifecycle. Planned maintenance drains services instead of casually destroying them.</p><div id=\"operator-metrics\" class=\"grid\"></div><section class=\"card section\"><h2>Nodes &amp; services</h2><div id=\"operator-overview\" class=\"list\"></div></section><section class=\"card section\"><h2>Storage capacity</h2><div id=\"operator-storage\" class=\"list\"></div></section><div class=\"grid section\"><section class=\"card\"><h2>Jobs &amp; queues</h2><pre id=\"operator-jobs\"></pre></section><section class=\"card\"><h2>Runtime backends</h2><pre id=\"operator-runtime\"></pre></section></div><p id=\"operator-status\" class=\"status\"></p>`,loadOperator);

  if(fq(\"operator-refresh\"))fq(\"operator-refresh\").onclick=loadOperator;
  if(fq(\"submission-create\"))fq(\"submission-create\").onclick=async()=>{try{await api(\"/api/v1/submissions\",{method:\"POST\",body:JSON.stringify({source_type:fq(\"submission-source\").value,source_reference:fq(\"submission-reference\").value,project_id:fq(\"submission-project\").value,collection_id:fq(\"submission-collection\").value,license_id:fq(\"submission-license\").value,consent_code:fq(\"submission-consent\").value})});loadIntakeReview()}catch(e){fq(\"intake-review-status\").textContent=e.message}};
  if(fq(\"review-create\"))fq(\"review-create\").onclick=async()=>{try{await api(\"/api/v1/review-cases\",{method:\"POST\",body:JSON.stringify({subject_type:fq(\"review-subject-type\").value,subject_id:fq(\"review-subject\").value,project_id:fq(\"review-project\").value,domain:fq(\"review-domain\").value,specialty:fq(\"review-specialty\").value,geography:fq(\"review-geography\").value})});loadIntakeReview()}catch(e){fq(\"intake-review-status\").textContent=e.message}};
  if(fq(\"review-determine\"))fq(\"review-determine\").onclick=async()=>{const id=fq(\"review-case-id\").value.trim();if(!id)return;try{await api(`/api/v1/review-cases/${encodeURIComponent(id)}/determinations`,{method:\"POST\",body:JSON.stringify({assertion:fq(\"review-assertion\").value,confidence:Number(fq(\"review-confidence\").value),evidence:{source:\"web-expert-review\"}})});loadReviewDetail(id);loadIntakeReview()}catch(e){fq(\"intake-review-status\").textContent=e.message}};
  if(fq(\"review-accept\"))fq(\"review-accept\").onclick=async()=>{const id=fq(\"review-case-id\").value.trim(),determination=fq(\"review-accept-id\").value.trim();if(!id||!determination)return;try{await api(`/api/v1/review-cases/${encodeURIComponent(id)}/accept`,{method:\"POST\",body:JSON.stringify({determination_id:determination})});loadReviewDetail(id);loadIntakeReview()}catch(e){fq(\"intake-review-status\").textContent=e.message}};
})();
"""


def rewrite_public_target(method: str, target: str) -> str:
    """Map short operational probe paths to the canonical public API paths."""
    if method != "GET":
        return target
    route = urlsplit(target)
    replacement = _HEALTH_ALIASES.get(route.path)
    return replacement if replacement is not None else target


def public_response(method: str, target: str) -> ApiResponse | None:
    """Return transport-level public documentation responses when applicable."""
    if method != "GET":
        return None
    path = urlsplit(target).path
    if path == "/openapi.json":
        return ApiResponse.json(200, openapi_document())
    if path in {"/docs", "/api-docs"}:
        return ApiResponse(200, _documentation_html(), "text/html; charset=utf-8")
    return None


def patch_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Apply the cross-client platform enhancement to the browser bundle once."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _WEB_PLATFORM_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _WEB_PLATFORM_PATCH,
        response.content_type,
        response.headers,
    )


def openapi_document() -> dict[str, object]:
    """Return the stable OpenAPI contract for current server/platform surfaces."""
    secured = [{"bearerAuth": []}]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Fieldora Server API",
            "version": __version__,
            "description": (
                "Governed Fieldora Platform API. Library evidence is organization-owned; "
                "project context is optional. Protected domain and operator endpoints "
                "remain subject to authentication and PBAC."
            ),
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Fieldora service/device API key using Bearer syntax.",
                },
            }
        },
        "paths": {
            "/api/v1/status": {
                "get": {"summary": "Server version/status", "responses": {"200": {"description": "Server status"}}}
            },
            "/api/v1/health/live": {
                "get": {"summary": "Liveness probe", "responses": {"200": {"description": "Process is live"}}}
            },
            "/api/v1/health/ready": {
                "get": {"summary": "Readiness probe", "responses": {"200": {"description": "Dependencies ready"}, "503": {"description": "Dependency unavailable"}}}
            },
            "/api/v1/session": {
                "post": {"summary": "Create session", "responses": {"200": {"description": "Session created"}, "401": {"description": "Authentication failed"}}},
                "delete": {"summary": "Revoke session", "security": secured, "responses": {"204": {"description": "Revoked"}}},
            },
            "/api/v1/me": {
                "get": {"summary": "Current identity", "security": secured, "responses": {"200": {"description": "Identity"}}}
            },
            "/api/v1/media": {
                "get": {"summary": "List governed Library evidence", "security": secured, "responses": {"200": {"description": "Media listing"}}}
            },
            "/api/v1/uploads": {
                "post": {"summary": "Begin Library upload; project_id is optional", "security": secured, "responses": {"201": {"description": "Upload created"}}}
            },
            "/api/v1/staged-submissions": {
                "post": {"summary": "Begin quarantined governed intake; project optional", "security": secured, "responses": {"201": {"description": "Staged submission created"}}}
            },
            "/api/v1/submissions": {
                "get": {"summary": "List scientific intake records", "security": secured, "responses": {"200": {"description": "Submissions"}}},
                "post": {"summary": "Register project-independent submission provenance", "security": secured, "responses": {"201": {"description": "Submission registered"}}},
            },
            "/api/v1/review-cases": {
                "get": {"summary": "List expert review cases", "security": secured, "responses": {"200": {"description": "Review cases"}}},
                "post": {"summary": "Request expert review", "security": secured, "responses": {"201": {"description": "Review requested"}}},
            },
            "/api/v1/operator/overview": {
                "get": {"summary": "Operator health, services, storage and queue overview", "security": secured, "responses": {"200": {"description": "Operator snapshot"}, "403": {"description": "Operator permission required"}}}
            },
            "/api/v1/operator/services": {
                "get": {"summary": "List enrolled services", "security": secured, "responses": {"200": {"description": "Service registry"}}},
                "post": {"summary": "Enroll durable service identity", "security": secured, "responses": {"201": {"description": "Service enrolled"}}},
            },
        },
    }


def _documentation_html() -> bytes:
    return b"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Fieldora API</title></head><body><main><h1>Fieldora Server API</h1><p>OpenAPI 3.1 contract: <a href=\"/openapi.json\">/openapi.json</a></p><h2>Operations probes</h2><ul><li><a href=\"/health/live\">/health/live</a></li><li><a href=\"/health/ready\">/health/ready</a></li></ul><p>Library uploads may be organization-scoped without a project. Scientific submissions, expert review and operator endpoints remain governed by Fieldora authentication and PBAC.</p></main></body></html>"""
