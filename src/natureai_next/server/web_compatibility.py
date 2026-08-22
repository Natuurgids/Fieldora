"""Compatibility surface for the Fieldora managed-server web client."""
from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next import __version__
from natureai_next.server.api import ApiResponse

_HEALTH_ALIASES = {
    "/health": "/api/v1/health/ready",
    "/health/live": "/api/v1/health/live",
    "/health/ready": "/api/v1/health/ready",
}

_WEB_PLATFORM_PATCH = br"""

/* Fieldora Platform: Library-first intake, collaboration, and operator surfaces. */
(()=>{
 const q=id=>document.getElementById(id);
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const oldProjectOptions=projectOptions;
 projectOptions=function(){oldProjectOptions();const s=q("upload-project");if(s){const o=s.querySelector('option[value=""]');if(o)o.textContent="General Library (no project)";const l=s.closest("label");if(l&&l.firstChild)l.firstChild.textContent="Project (optional)";}};
 const sp=q("stage-project");if(sp){sp.placeholder="Leave empty for General Library";const l=sp.closest("label");if(l&&l.firstChild)l.firstChild.textContent="Project ID (optional)";}

 async function generalUpload(){
  const file=q("upload-file")?.files?.[0],project=q("upload-project")?.value||"";
  if(!file)return status("upload-status","Choose a file. Project is optional.",true);
  status("upload-status","Calculating SHA-256…");
  const bytes=await file.arrayBuffer(),digest=await crypto.subtle.digest("SHA-256",bytes);
  const hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
  try{
   const begun=await api("/api/v1/uploads",{method:"POST",body:JSON.stringify({project_id:project,filename:file.name,mime_type:file.type,size_bytes:file.size,sha256:hash})});
   let result=null;for(let start=0;start<file.size;start+=4*1024*1024){const end=Math.min(file.size,start+4*1024*1024);result=await api(`/api/v1/uploads/${begun.upload_id}`,{method:"PUT",headers:{"Content-Range":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});status("upload-status",`Uploaded ${Math.round(end/file.size*100)}%`);}
   status("upload-status",`Verified · ${project?"project-linked":"General Library"} · ${result?.media_id||""}`);loadMedia();
  }catch(e){status("upload-status",e.message,true)}
 }
 async function stagedUploadGeneral(){
  const files=[...(q("stage-files")?.files||[])],project=q("stage-project")?.value?.trim()||"";
  if(!files.length)return status("stage-status","Choose one or more files. Project is optional.",true);
  try{
   const created=await api("/api/v1/staged-submissions",{method:"POST",body:JSON.stringify({project_id:project,contract_id:q("stage-contract")?.value||"",publication_policy:q("stage-policy")?.value||"review",expected_files:files.length})}),sid=created.submission.submission_id;
   for(const file of files){const bytes=await file.arrayBuffer(),digest=await crypto.subtle.digest("SHA-256",bytes),hash=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");const begun=await api(`/api/v1/staged-submissions/${sid}/files`,{method:"POST",body:JSON.stringify({filename:file.name,relative_path:file.webkitRelativePath||file.name,mime_type:file.type,size_bytes:file.size,sha256:hash})});for(let start=0;start<file.size;start+=4*1024*1024){const end=Math.min(file.size,start+4*1024*1024);await api(`/api/v1/staged-files/${begun.staged_file_id}`,{method:"PUT",headers:{"Content-Range":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)})}}
   await api(`/api/v1/staged-submissions/${sid}/seal`,{method:"POST",body:"{}"});await api(`/api/v1/staged-submissions/${sid}/process`,{method:"POST",body:"{}"});status("stage-status",`Submission ${sid} · ${project?"project context":"General Library"}`);
  }catch(e){status("stage-status",e.message,true)}
 }
 function replace(id,handler){const old=q(id);if(!old)return;const fresh=old.cloneNode(true);old.replaceWith(fresh);fresh.onclick=handler;}
 replace("upload-start",generalUpload);replace("stage-start",stagedUploadGeneral);
 document.querySelectorAll(".go-import").forEach(b=>b.onclick=()=>{showPage("library");q("import-card")?.scrollIntoView({behavior:"smooth",block:"start"});const p=q("upload-file");if(p){p.focus();p.click();}});

 function addPage(name,icon,title,html,loader){const nav=document.querySelector(".sidebar nav"),main=document.querySelector("main.main");if(!nav||!main||q(`page-${name}`))return;const b=document.createElement("button");b.className="nav";b.dataset.page=name;b.innerHTML=`<span class="nav-icon">${icon}</span>${esc(title)}`;b.onclick=()=>{showPage(name);loader()};nav.appendChild(b);const p=document.createElement("section");p.className="page";p.id=`page-${name}`;p.hidden=true;p.innerHTML=html;main.appendChild(p);}
 async function loadCollaboration(){try{const [s,r]=await Promise.all([api("/api/v1/submissions?limit=100"),api("/api/v1/review-cases?limit=100")]);q("platform-submissions").innerHTML=(s.items||[]).map(x=>`<div class="row"><strong>${esc(x.source_type)}</strong><span>${esc(x.project_id||"General Library")}</span><span>${esc(x.state)}</span><span>${esc(x.submission_id)}</span></div>`).join("")||'<div class="empty">No submissions.</div>';q("platform-reviews").innerHTML=(r.items||[]).map(x=>`<button class="row review-row" data-id="${esc(x.review_case_id)}"><strong>${esc(x.domain)}</strong><span>${esc(x.specialty||"General")}</span><span>${esc(x.state)}</span><span>${esc(x.subject_id)}</span></button>`).join("")||'<div class="empty">No review cases.</div>';document.querySelectorAll(".review-row").forEach(b=>b.onclick=()=>{q("review-case-id").value=b.dataset.id;loadReview(b.dataset.id)})}catch(e){q("collab-status").textContent=e.message}}
 async function loadReview(id){try{const x=await api(`/api/v1/review-cases/${encodeURIComponent(id)}`);q("review-detail").innerHTML=`<p><strong>${esc(x.review_case.domain)}</strong> · ${esc(x.review_case.state)}</p>`+(x.determinations||[]).map(d=>`<div class="row"><strong>${esc(d.assertion)}</strong><span>${Math.round(Number(d.confidence)*100)}%</span><span>${esc(d.expert_id)}</span><span>${esc(d.determination_id)}</span></div>`).join("")}catch(e){q("review-detail").textContent=e.message}}
 addPage("intake-review","◇","Intake & Review",`<div class="top"><h1>Intake &amp; Expert Review</h1></div><p class="muted">Evidence can enter the governed Library without a project. Review cases route it to expert domains while preserving every determination.</p><div class="grid"><section class="card"><h2>Submission</h2><div class="form-grid"><label>Source<input id="submission-source" value="external-contributor"></label><label>Reference<input id="submission-reference"></label><label>Project (optional)<input id="submission-project"></label><label>Collection (optional)<input id="submission-collection"></label><label>License / rights<input id="submission-license"></label><label>Consent<input id="submission-consent"></label></div><button id="submission-create" class="primary section">Register submission</button></section><section class="card"><h2>Expert review</h2><div class="form-grid"><label>Subject type<input id="review-subject-type" value="asset"></label><label>Subject ID<input id="review-subject"></label><label>Project (optional)<input id="review-project"></label><label>Domain<input id="review-domain" placeholder="taxonomy, pathology, geology…"></label><label>Specialty<input id="review-specialty"></label><label>Geography<input id="review-geography"></label></div><button id="review-create" class="primary section">Request review</button></section></div><section class="card section"><h2>Submissions</h2><div id="platform-submissions" class="list"></div></section><section class="card section"><h2>Review queue</h2><div id="platform-reviews" class="list"></div></section><section class="card section"><h2>Determination</h2><div class="form-grid"><label>Review case<input id="review-case-id"></label><label>Assertion<input id="review-assertion"></label><label>Confidence<input id="review-confidence" type="number" min="0" max="1" step=".01" value="0.8"></label><label>Accept ID<input id="review-accept-id"></label></div><div class="actions section"><button id="review-determine" class="primary">Add determination</button><button id="review-accept">Accept</button></div><div id="review-detail" class="section"></div></section><p id="collab-status" class="status"></p>`,loadCollaboration);

 async function loadOperator(){try{const d=await api("/api/v1/operator/overview",{purpose:"administration"}),c=d.service_counts||{};q("operator-metrics").innerHTML=[["Active",c.active||0],["Draining",c.draining||0],["Stale",d.stale_service_count||0],["Certificates expiring",d.expiring_certificate_count||0]].map(x=>`<section class="card metric"><span class="muted">${esc(x[0])}</span><strong>${esc(x[1])}</strong></section>`).join("");q("operator-services").innerHTML=(d.services||[]).map(s=>`<div class="row"><strong>${esc(s.name)}</strong><span>${esc(s.service_type)} · ${esc(s.node_name)}</span><span class="pill">${esc(s.state)}</span><span>${["drain","activate","stop","revoke"].map(op=>`<button ${op==="revoke"?'class="danger"':''} data-op="${op}" data-service="${esc(s.service_id)}">${op}</button>`).join(" ")}</span></div>`).join("")||'<div class="empty">No enrolled services.</div>';q("operator-storage").innerHTML=(d.storage||[]).map(s=>`<div class="row"><strong>${esc(s.path)}</strong><span>${(s.used_bytes/1073741824).toFixed(2)} GiB used</span><span>${(s.free_bytes/1073741824).toFixed(2)} GiB free</span><span>${esc(s.used_percent)}%</span></div>`).join("");q("operator-jobs").textContent=JSON.stringify(d.jobs||{},null,2);document.querySelectorAll("[data-op][data-service]").forEach(b=>b.onclick=async()=>{try{await api(`/api/v1/operator/services/${b.dataset.service}/${b.dataset.op}`,{method:"POST",purpose:"administration",body:"{}"});loadOperator()}catch(e){q("operator-status").textContent=e.message}})}catch(e){q("operator-services").textContent=e.message}}
 addPage("operator","◉","Operator",`<div class="top"><h1>Fieldora Operator</h1><button id="operator-refresh">Refresh</button></div><p class="muted">Durable enrolled services, capacity, queues, certificates and lifecycle. Maintenance drains rather than casually destroying services.</p><div id="operator-metrics" class="grid"></div><section class="card section"><h2>Nodes &amp; services</h2><div id="operator-services" class="list"></div></section><section class="card section"><h2>Storage</h2><div id="operator-storage" class="list"></div></section><section class="card section"><h2>Jobs &amp; queues</h2><pre id="operator-jobs"></pre></section><p id="operator-status" class="status"></p>`,loadOperator);
 q("operator-refresh")?.addEventListener("click",loadOperator);
 q("submission-create")?.addEventListener("click",async()=>{try{await api("/api/v1/submissions",{method:"POST",body:JSON.stringify({source_type:q("submission-source").value,source_reference:q("submission-reference").value,project_id:q("submission-project").value,collection_id:q("submission-collection").value,license_id:q("submission-license").value,consent_code:q("submission-consent").value})});loadCollaboration()}catch(e){q("collab-status").textContent=e.message}});
 q("review-create")?.addEventListener("click",async()=>{try{await api("/api/v1/review-cases",{method:"POST",body:JSON.stringify({subject_type:q("review-subject-type").value,subject_id:q("review-subject").value,project_id:q("review-project").value,domain:q("review-domain").value,specialty:q("review-specialty").value,geography:q("review-geography").value})});loadCollaboration()}catch(e){q("collab-status").textContent=e.message}});
 q("review-determine")?.addEventListener("click",async()=>{const id=q("review-case-id").value.trim();if(!id)return;try{await api(`/api/v1/review-cases/${encodeURIComponent(id)}/determinations`,{method:"POST",body:JSON.stringify({assertion:q("review-assertion").value,confidence:Number(q("review-confidence").value),evidence:{source:"web-expert-review"}})});loadReview(id);loadCollaboration()}catch(e){q("collab-status").textContent=e.message}});
 q("review-accept")?.addEventListener("click",async()=>{const id=q("review-case-id").value.trim(),det=q("review-accept-id").value.trim();if(!id||!det)return;try{await api(`/api/v1/review-cases/${encodeURIComponent(id)}/accept`,{method:"POST",body:JSON.stringify({determination_id:det})});loadReview(id);loadCollaboration()}catch(e){q("collab-status").textContent=e.message}});
})();
"""


def rewrite_public_target(method: str, target: str) -> str:
    if method != "GET":
        return target
    replacement = _HEALTH_ALIASES.get(urlsplit(target).path)
    return replacement if replacement is not None else target


def public_response(method: str, target: str) -> ApiResponse | None:
    if method != "GET":
        return None
    path = urlsplit(target).path
    if path == "/openapi.json":
        return ApiResponse.json(200, openapi_document())
    if path in {"/docs", "/api-docs"}:
        return ApiResponse(200, _documentation_html(), "text/html; charset=utf-8")
    return None


def patch_web_response(target: str, response: ApiResponse) -> ApiResponse:
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
    secured = [{"bearerAuth": []}]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Fieldora Server API",
            "version": __version__,
            "description": (
                "Governed Fieldora Platform API. Library evidence is organization-owned; "
                "project context is optional."
            ),
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
        "paths": {
            "/api/v1/status": {"get": {"summary": "Server status", "responses": {"200": {"description": "OK"}}}},
            "/api/v1/health/live": {"get": {"summary": "Liveness", "responses": {"200": {"description": "Live"}}}},
            "/api/v1/health/ready": {"get": {"summary": "Readiness", "responses": {"200": {"description": "Ready"}, "503": {"description": "Unavailable"}}}},
            "/api/v1/media": {"get": {"summary": "List Library media", "security": secured, "responses": {"200": {"description": "Items"}}}},
            "/api/v1/uploads": {"post": {"summary": "Begin resumable Library upload; project optional", "security": secured, "responses": {"201": {"description": "Upload"}}}},
            "/api/v1/staged-submissions": {"post": {"summary": "Begin staged Library intake; project optional", "security": secured, "responses": {"201": {"description": "Submission"}}}},
            "/api/v1/submissions": {"get": {"summary": "List intake records", "security": secured, "responses": {"200": {"description": "Items"}}}, "post": {"summary": "Register submission provenance", "security": secured, "responses": {"201": {"description": "Created"}}}},
            "/api/v1/review-cases": {"get": {"summary": "List expert review cases", "security": secured, "responses": {"200": {"description": "Items"}}}, "post": {"summary": "Request expert review", "security": secured, "responses": {"201": {"description": "Created"}}}},
            "/api/v1/operator/overview": {"get": {"summary": "Operator overview", "security": secured, "responses": {"200": {"description": "Snapshot"}, "403": {"description": "Forbidden"}}}},
            "/api/v1/operator/services": {"get": {"summary": "List enrolled services", "security": secured, "responses": {"200": {"description": "Services"}}}, "post": {"summary": "Enroll service", "security": secured, "responses": {"201": {"description": "Enrolled"}}}},
            "/api/v1/facility-planning/plans": {"get": {"summary": "List future layouts", "security": secured, "responses": {"200": {"description": "Layouts"}}}, "post": {"summary": "Create future layout", "security": secured, "responses": {"201": {"description": "Created"}}}},
            "/api/v1/facility-planning/campaigns": {"get": {"summary": "List relocation campaigns", "security": secured, "responses": {"200": {"description": "Campaigns"}}}, "post": {"summary": "Create relocation campaign", "security": secured, "responses": {"201": {"description": "Created"}}}},
        },
    }


def _documentation_html() -> bytes:
    return b"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fieldora API</title></head><body><main><h1>Fieldora Server API</h1><p><a href="/openapi.json">OpenAPI 3.1 contract</a></p><ul><li><a href="/health/live">Liveness</a></li><li><a href="/health/ready">Readiness</a></li></ul><p>Library uploads may be organization-scoped without a project. Scientific collaboration and operator endpoints remain governed by authentication and PBAC.</p></main></body></html>"""
