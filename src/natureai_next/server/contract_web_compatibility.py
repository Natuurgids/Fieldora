"""Browser workspace for governed evidence contracts and Chinese-wall administration."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_CONTRACT_WEB_PATCH = bytes(
    r"""

/* Fieldora governed Data Access & Contracts workspace. */
(()=>{
 const q=id=>document.getElementById(id);if(q("page-data-access"))return;
 const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const nav=document.querySelector(".sidebar nav"),main=document.querySelector("main.main");if(!nav||!main)return;
 const b=document.createElement("button");b.className="nav";b.dataset.page="data-access";b.innerHTML='<span class="nav-icon">▣</span>Data Access';nav.appendChild(b);
 const p=document.createElement("section");p.className="page";p.id="page-data-access";p.hidden=true;p.innerHTML=`<div class="top"><h1>Data Access &amp; Contracts</h1><button id="contract-load">Load subject</button></div><p class="muted">Evidence keeps its original source and ownership. Contracts only grant or restrict access. Evidence-owner restrictions are upstream and cannot be overridden by a project owner.</p><div class="grid"><section class="card"><h2>Contract subject</h2><div class="form-grid"><label>Type<select id="contract-subject-kind"><option value="asset">Library asset</option><option value="collection">Collection / dataset</option></select></label><label>Subject ID<input id="contract-subject-id"></label></div><div id="contract-current" class="section"></div></section><section class="card"><h2>Recipient scope</h2><div class="form-grid"><label>Scope<select id="contract-target-kind"><option value="organization">Organization</option><option value="project">Project</option><option value="organization_project">Organization + project</option><option value="all">All governed users allowed by PBAC</option></select></label><label>Organization ID<input id="contract-target-org"></label><label>Project ID<input id="contract-target-project"></label></div><div class="actions section"><button id="contract-restrict">Replace / narrow</button><button id="contract-share" class="primary">Request sharing</button></div><p class="muted">All-access is not public access. Normal authentication and PBAC still apply.</p></section></div><div class="grid section"><section class="card"><h2>Evidence-owner ceiling</h2><label>Evidence owner identity<input id="evidence-owner-id"></label><button id="evidence-owner-set" class="section">Set owner ceiling to recipient scope</button><div id="evidence-owner-current" class="section"></div></section><section class="card"><h2>Source project owner</h2><div class="form-grid"><label>Source project ID<input id="contract-source-project"></label><label>Owner identity<input id="project-owner-id"></label></div><div class="actions section"><button id="project-owner-load">Load owner</button><button id="project-owner-set">Set owner</button></div><div id="project-owner-current" class="section"></div></section></div><section class="card section"><h2>Project-owner approval</h2><p class="muted">Project-governed sharing remains pending until the recorded source project owner makes two separate attestations. Neither attestation can override an evidence-owner ceiling.</p><div class="form-grid"><label>Pending contract ID<input id="contract-pending-id"></label><label>Attestation reference<input id="contract-signature-id" placeholder="reason/ticket/attestation reference"></label></div><button id="contract-sign">Record owner attestation</button><div id="contract-signatures" class="section"></div></section><p id="contract-status" class="status"></p>`;main.appendChild(p);
 function target(){const kind=q("contract-target-kind").value,organization_id=q("contract-target-org").value.trim(),project_id=q("contract-target-project").value.trim();return {kind,organization_id,project_id}}
 function subject(){return {kind:q("contract-subject-kind").value,id:q("contract-subject-id").value.trim()}}
 function renderContract(c,sigs=[]){if(!c)return '<div class="empty">No active contract.</div>';const targets=(c.targets||[]).map(t=>`${esc(t.kind)} ${esc(t.organization_id||"")} ${esc(t.project_id||"")}`).join("<br>");return `<div class="row"><strong>${esc(c.status)}</strong><span>${targets}</span><span>${esc(c.source_project_id||"No project")}</span><span>${esc(c.contract_id)}</span></div><p class="muted">Owner attestations: ${sigs.length}/${c.required_owner_signatures||0}</p>`}
 async function loadSubject(){const s=subject();if(!s.id)return;try{const x=await api(`/api/v1/access-barriers?subject_kind=${encodeURIComponent(s.kind)}&subject_id=${encodeURIComponent(s.id)}`,{purpose:"administration"});q("contract-current").innerHTML=renderContract(x.contract,x.signatures||[]);if(x.contract?.source_project_id)q("contract-source-project").value=x.contract.source_project_id;const o=await api(`/api/v1/access-barriers/evidence/${encodeURIComponent(s.kind)}/${encodeURIComponent(s.id)}/owner-contract`,{purpose:"administration"});q("evidence-owner-current").innerHTML=o.owner_contract?`<div class="row"><strong>${esc(o.owner_contract.owner_identity)}</strong><span>${(o.owner_contract.targets||[]).map(t=>esc(t.kind+" "+(t.organization_id||"")+" "+(t.project_id||""))).join("; ")}</span></div>`:'<div class="empty">No evidence-owner ceiling.</div>';q("contract-status").textContent="Contract subject loaded."}catch(e){q("contract-status").textContent=e.message}}
 async function change(mode){const s=subject();if(!s.id)return;try{const x=await api("/api/v1/access-barriers",{method:"POST",purpose:"administration",body:JSON.stringify({subject_kind:s.kind,subject_id:s.id,mode,targets:[target()]})});q("contract-pending-id").value=x.contract.contract_id;q("contract-status").textContent=x.contract.status==="pending"?"Sharing request is pending two project-owner attestations.":"Contract activated.";loadSubject()}catch(e){q("contract-status").textContent=e.message}}
 async function setEvidenceOwner(){const s=subject(),owner=q("evidence-owner-id").value.trim();if(!s.id||!owner)return;try{await api(`/api/v1/access-barriers/evidence/${encodeURIComponent(s.kind)}/${encodeURIComponent(s.id)}/owner-contract`,{method:"POST",purpose:"administration",body:JSON.stringify({owner_identity:owner,targets:[target()]})});q("contract-status").textContent="Evidence-owner ceiling saved.";loadSubject()}catch(e){q("contract-status").textContent=e.message}}
 async function loadProjectOwner(){const id=q("contract-source-project").value.trim();if(!id)return;try{const x=await api(`/api/v1/access-barriers/projects/${encodeURIComponent(id)}/owner`,{purpose:"administration"});q("project-owner-current").textContent=x.owner?`Owner: ${x.owner.owner_identity}`:"No recorded project owner."}catch(e){q("contract-status").textContent=e.message}}
 async function setProjectOwner(){const id=q("contract-source-project").value.trim(),owner=q("project-owner-id").value.trim();if(!id||!owner)return;try{await api(`/api/v1/access-barriers/projects/${encodeURIComponent(id)}/owner`,{method:"POST",purpose:"administration",body:JSON.stringify({owner_identity:owner})});q("contract-status").textContent="Source project owner saved.";loadProjectOwner()}catch(e){q("contract-status").textContent=e.message}}
 async function sign(){const id=q("contract-pending-id").value.trim(),signature_id=q("contract-signature-id").value.trim();if(!id||!signature_id)return;try{const x=await api(`/api/v1/access-barriers/${encodeURIComponent(id)}/sign`,{method:"POST",purpose:"administration",body:JSON.stringify({signature_id})});q("contract-signatures").innerHTML=renderContract(x.contract,x.signatures||[]);q("contract-status").textContent=x.contract.status==="active"?"Sharing contract is active.":"First attestation recorded; one separate owner attestation is still required.";q("contract-signature-id").value="";loadSubject()}catch(e){q("contract-status").textContent=e.message}}
 b.onclick=()=>{showPage("data-access");loadSubject()};q("contract-load").onclick=loadSubject;q("contract-restrict").onclick=()=>change("restrict");q("contract-share").onclick=()=>change("share");q("evidence-owner-set").onclick=setEvidenceOwner;q("project-owner-load").onclick=loadProjectOwner;q("project-owner-set").onclick=setProjectOwner;q("contract-sign").onclick=sign;
})();
""",
    "utf-8",
)


def patch_contract_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _CONTRACT_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _CONTRACT_WEB_PATCH,
        response.content_type,
        response.headers,
    )
