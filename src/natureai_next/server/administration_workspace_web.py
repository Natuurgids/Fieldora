"""Grouped Administration navigation for the managed Fieldora web client."""

from natureai_next.server.api import ApiResponse

_ADMINISTRATION_WORKSPACE_PATCH = bytes(
    r"""

/* Fieldora Administration alignment: preserve every protected destination while
   grouping them into understandable management domains. Audit is its own governed
   workspace so its API authority can be projected independently from Governance. */
(()=>{
 if(window.__fieldoraAdministrationWorkspaceWired)return;
 window.__fieldoraAdministrationWorkspaceWired=true;
 const style=document.createElement("style");
 style.textContent=`
  .administration-workspace-nav{align-items:flex-start;gap:14px}
  .administration-nav-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding-right:12px;border-right:1px solid var(--line)}
  .administration-nav-group:last-child{border-right:0;padding-right:0}
  .administration-nav-group-label{width:100%;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:0 4px 2px}
 `;
 document.head.appendChild(style);

 const governance=document.getElementById("page-administration");
 const auditCard=document.getElementById("audit-list")?.closest(".card");
 let auditPage=document.getElementById("page-audit");
 if(governance&&auditCard&&!auditPage){
  auditPage=document.createElement("section");
  auditPage.className="page";
  auditPage.id="page-audit";
  auditPage.hidden=true;
  const top=document.createElement("div");
  top.className="top";
  top.innerHTML='<h1>Audit</h1><button id="audit-refresh" class="primary" type="button">Refresh</button>';
  auditPage.appendChild(top);
  auditPage.appendChild(auditCard);
  governance.after(auditPage);
  document.getElementById("audit-refresh").onclick=()=>loadAudit();
 }

 /* Governance must not implicitly fetch Audit. The Audit workspace invokes the
    already-governed /api/v1/audit contract only when that destination is opened. */
 if(typeof loadAdministration==="function"){
  loadAdministration=async function(){await Promise.all([loadRuntime(),loadContracts("contracts")])};
 }
 const administrationShowPage=showPage;
 showPage=function(page){
  administrationShowPage(page);
  if(page==="audit")loadAudit();
 };

 const groups=[
  ["Governance & review",["administration","audit","intake-review","reference"]],
  ["Operations",["operations","connectors"]],
  ["Platform services",["aiadmin","operator","platform"]],
 ];
 const adminPages=["administration","audit","operations","intake-review","aiadmin","reference","connectors","operator","platform"];
 const existingAdminNav=governance?.querySelector(".workspace-subnav");
 if(auditPage&&existingAdminNav&&!auditPage.querySelector(".workspace-subnav")){
  const cloned=existingAdminNav.cloneNode(true);
  cloned.querySelectorAll("[data-workspace-target]").forEach(button=>{
   button.onclick=()=>showPage(button.dataset.workspaceTarget);
  });
  auditPage.querySelector(".top")?.after(cloned);
 }
 adminPages.forEach(page=>{
  const host=document.getElementById(`page-${page}`);
  const nav=host?.querySelector(".workspace-subnav");
  if(!nav)return;
  if(!nav.querySelector('[data-workspace-target="audit"]')&&auditPage){
   const button=document.createElement("button");
   button.type="button";
   button.dataset.workspaceTarget="audit";
   button.textContent="Audit";
   button.onclick=()=>showPage("audit");
   nav.appendChild(button);
  }
  if(nav.dataset.administrationGrouped)return;
  const buttons=new Map(
   [...nav.querySelectorAll("[data-workspace-target]")].map(button=>[
    button.dataset.workspaceTarget,
    button,
   ])
  );
  nav.replaceChildren();
  nav.classList.add("administration-workspace-nav");
  nav.dataset.administrationGrouped="true";
  groups.forEach(([label,targets])=>{
   const group=document.createElement("div");
   group.className="administration-nav-group";
   group.setAttribute("role","group");
   group.setAttribute("aria-label",label);
   const heading=document.createElement("span");
   heading.className="administration-nav-group-label";
   heading.textContent=label;
   group.appendChild(heading);
   targets.forEach(target=>{
    const button=buttons.get(target);
    if(button)group.appendChild(button);
   });
   nav.appendChild(group);
  });
 });
})();
""",
    "utf-8",
)


def patch_administration_workspace_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _ADMINISTRATION_WORKSPACE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _ADMINISTRATION_WORKSPACE_PATCH,
        response.content_type,
        response.headers,
    )