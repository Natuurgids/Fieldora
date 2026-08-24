"""Desktop-aligned information architecture for the managed Fieldora web client."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


_DESKTOP_ALIGNMENT_PATCH = bytes(
    r"""

/* Fieldora desktop/server alignment: one stable workspace model and one Import action. */
(()=>{
 if(window.__fieldoraDesktopAlignmentWired)return;window.__fieldoraDesktopAlignmentWired=true;
 const q=id=>document.getElementById(id);
 const style=document.createElement("style");
 style.textContent=`
  .workspace-subnav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:-4px 0 16px;padding:8px 0;border-bottom:1px solid var(--line)}
  .workspace-subnav button{background:transparent;padding:7px 10px;color:var(--muted)}
  .workspace-subnav button[aria-selected="true"]{color:#fff;border-color:var(--green);background:#203b32}
  .nav-section-label{margin:10px 10px 3px;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
  .import-menu{position:fixed;z-index:1000;display:grid;min-width:220px;padding:7px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 30px #0008}
  .import-menu[hidden]{display:none!important}.import-menu button{border:0;background:transparent;text-align:left}.import-menu button:hover{background:#203b32}
  .import-source-summary{color:var(--muted);font-size:13px;margin-top:8px}
 `;
 document.head.appendChild(style);

 const desktopMain=[
  ["home","⌂","Home"],
  ["library","▣","Library"],
  ["observations","◎","Observations"],
  ["research","⚗","Research"],
  ["knowledge","◫","Knowledge & AI"],
  ["administration","⚙","Administration"],
  ["help","?","Help & Guides"],
 ];
 const researchPages=[
  ["projects","Projects & Portfolio"],
  ["research","Research records"],
  ["dossiers","Dossiers"],
  ["capacity","Capacity"],
 ];
 const adminPages=[
  ["administration","Governance"],
  ["operations","Assets & Facilities"],
  ["intake-review","Intake & Review"],
  ["aiadmin","AI Platform"],
  ["reference","Reference Data"],
  ["connectors","Connectors"],
  ["operator","Operator"],
  ["platform","Platform"],
 ];
 const groupFor=page=>researchPages.some(x=>x[0]===page)?"research":adminPages.some(x=>x[0]===page)?"administration":page;

 const sidebar=document.querySelector(".sidebar nav");
 if(sidebar){
  const existing=new Map([...sidebar.querySelectorAll(".nav[data-page]")].map(b=>[b.dataset.page,b]));
  sidebar.replaceChildren();
  const science=document.createElement("div");science.className="nav-section-label";science.textContent="Science workspace";sidebar.appendChild(science);
  desktopMain.slice(0,5).forEach(([page,icon,label])=>{
   const b=existing.get(page)||document.createElement("button");b.className="nav";b.dataset.page=page;b.innerHTML=`<span class="nav-icon">${icon}</span>${label}`;b.onclick=()=>showPage(page);sidebar.appendChild(b);
  });
  const management=document.createElement("div");management.className="nav-section-label";management.textContent="Platform management";sidebar.appendChild(management);
  desktopMain.slice(5).forEach(([page,icon,label])=>{
   const b=existing.get(page)||document.createElement("button");b.className="nav";b.dataset.page=page;b.innerHTML=`<span class="nav-icon">${icon}</span>${label}`;b.onclick=()=>showPage(page);sidebar.appendChild(b);
  });
 }

 function addSubnav(entries){
  entries.forEach(([page])=>{
   const host=q(`page-${page}`);if(!host||host.querySelector(".workspace-subnav"))return;
   const nav=document.createElement("div");nav.className="workspace-subnav";nav.setAttribute("role","tablist");
   entries.forEach(([target,label])=>{
    if(!q(`page-${target}`))return;
    const b=document.createElement("button");b.type="button";b.dataset.workspaceTarget=target;b.textContent=label;b.onclick=()=>showPage(target);nav.appendChild(b);
   });
   const top=host.querySelector(".top");if(top)top.after(nav);else host.prepend(nav);
  });
 }
 addSubnav(researchPages);addSubnav(adminPages);

 const alignedShowPage=showPage;
 showPage=function(page){
  alignedShowPage(page);
  const group=groupFor(page);
  document.querySelectorAll(".sidebar .nav[data-page]").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.page===group)));
  document.querySelectorAll(".workspace-subnav [data-workspace-target]").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.workspaceTarget===page)));
 };

 const menu=document.createElement("div");menu.id="fieldora-import-menu";menu.className="import-menu";menu.hidden=true;menu.setAttribute("role","menu");
 menu.innerHTML='<button type="button" data-import-source="files" role="menuitem">Files…</button><button type="button" data-import-source="folder" role="menuitem">Folder with subfolders…</button>';
 document.body.appendChild(menu);
 let importAnchor=null;
 function closeImportMenu(){menu.hidden=true;importAnchor=null}
 function openImportMenu(button){
  importAnchor=button;const r=button.getBoundingClientRect();menu.style.left=`${Math.max(8,Math.min(r.left,innerWidth-240))}px`;menu.style.top=`${Math.min(r.bottom+6,innerHeight-110)}px`;menu.hidden=false;
 }
 document.addEventListener("click",e=>{if(!menu.hidden&&!menu.contains(e.target)&&e.target!==importAnchor)closeImportMenu()});
 document.addEventListener("keydown",e=>{if(e.key==="Escape")closeImportMenu()});
 document.querySelectorAll(".go-import").forEach(button=>{
  button.textContent="＋ Import";button.setAttribute("aria-haspopup","menu");button.onclick=e=>{e.preventDefault();e.stopPropagation();menu.hidden?openImportMenu(button):closeImportMenu()};
 });
 const uploadInput=q("upload-file");
 if(uploadInput){const label=uploadInput.closest("label");if(label)label.hidden=true;}
 const oldFolderButton=q("upload-folder");if(oldFolderButton)oldFolderButton.closest(".import-source-actions")?.remove();
 const folderInput=q("upload-folder-input");
 const sourceSummary=document.createElement("p");sourceSummary.id="import-source-summary";sourceSummary.className="import-source-summary";sourceSummary.textContent="Choose Files or Folder from Import.";
 q("import-card")?.querySelector(".form-grid")?.after(sourceSummary);
 if(uploadInput)uploadInput.addEventListener("change",()=>{const n=uploadInput.files?.length||0;sourceSummary.textContent=n?`${n} file${n===1?"":"s"} selected for governed import.`:"Choose Files or Folder from Import."});
 menu.querySelector('[data-import-source="files"]').onclick=()=>{closeImportMenu();showPage("library");q("import-card")?.scrollIntoView({behavior:"smooth",block:"start"});uploadInput?.click()};
 menu.querySelector('[data-import-source="folder"]').onclick=()=>{closeImportMenu();showPage("library");q("import-card")?.scrollIntoView({behavior:"smooth",block:"start"});folderInput?.click()};
 const uploadButton=q("upload-start");if(uploadButton)uploadButton.textContent="Import selected files";

 const active=(location.hash||"#home").slice(1);if(q(`page-${active}`))showPage(active);else showPage("home");
})();
""",
    "utf-8",
)


def patch_desktop_alignment_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _DESKTOP_ALIGNMENT_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _DESKTOP_ALIGNMENT_PATCH,
        response.content_type,
        response.headers,
    )
