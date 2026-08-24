"""Desktop-aligned information architecture for the managed Fieldora web client."""

from natureai_next.server.api import ApiResponse

_DESKTOP_ALIGNMENT_PATCH = bytes(
    r"""

/* Fieldora desktop/server alignment: stable workspaces, coherent Library, one Import action. */
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
  .library-workspace-intro{margin:-6px 0 14px;color:var(--muted);max-width:880px}
  #library-browse-panel[hidden],#linked-storage-card[hidden],#import-card[hidden]{display:none!important}
  .home-science-focus,.research-workspace-intro{margin:-6px 0 14px;color:var(--muted);max-width:920px}
  .home-primary-actions{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-top:0}
  .home-primary-actions .card{display:grid;gap:8px;align-content:start}.home-primary-actions .card p{margin:0;color:var(--muted)}
  .home-primary-actions button{text-align:left;font-weight:600}
  .home-overview-label{margin:18px 0 8px;font-size:15px;color:var(--muted);font-weight:600}
  .home-system-context summary{cursor:pointer;font-weight:600}.home-system-context[open] summary{margin-bottom:12px}
  #research-legacy-projects[hidden],#research-legacy-related[hidden]{display:none!important}
  .research-records-card>h2{font-size:20px}.research-context-note{margin:0 0 12px;color:var(--muted)}
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

 /* The Library is one workspace with three clear tasks instead of a vertical
    accumulation of unrelated cards. Existing evidence controls remain intact. */
 const library=q("page-library");
 let libraryView="browse";
 let librarySubnav=null;
 let libraryBrowsePanel=null;
 function ensureLibraryStructure(){
  if(!library)return;
  if(!librarySubnav){
   const top=library.querySelector(".top");
   librarySubnav=document.createElement("div");librarySubnav.id="library-workspace-nav";librarySubnav.className="workspace-subnav";librarySubnav.setAttribute("role","tablist");
   [["browse","Browse evidence"],["linked","Linked archives"],["import","Import"]].forEach(([view,label])=>{
    const b=document.createElement("button");b.type="button";b.dataset.libraryView=view;b.textContent=label;b.onclick=()=>setLibraryView(view);librarySubnav.appendChild(b);
   });
   const intro=document.createElement("p");intro.id="library-workspace-intro";intro.className="library-workspace-intro";
   if(top){top.after(librarySubnav);librarySubnav.after(intro)}else{library.prepend(librarySubnav);librarySubnav.after(intro)}
  }
  if(!libraryBrowsePanel){
   const mediaTabs=[...library.children].find(node=>node.classList?.contains("tabs"));
   const evidenceSplit=[...library.children].find(node=>node.classList?.contains("split")&&node.querySelector?.("#media-grid"));
   if(mediaTabs||evidenceSplit){
    libraryBrowsePanel=document.createElement("section");libraryBrowsePanel.id="library-browse-panel";
    if(mediaTabs){mediaTabs.before(libraryBrowsePanel);libraryBrowsePanel.appendChild(mediaTabs)}
    if(evidenceSplit)libraryBrowsePanel.appendChild(evidenceSplit);
   }
  }
  applyLibraryView();
 }
 function applyLibraryView(){
  if(!library)return;
  const linked=q("linked-storage-card"),importCard=q("import-card"),intro=q("library-workspace-intro");
  if(libraryBrowsePanel)libraryBrowsePanel.hidden=libraryView!=="browse";
  if(linked)linked.hidden=libraryView!=="linked";
  if(importCard)importCard.hidden=libraryView!=="import";
  librarySubnav?.querySelectorAll("[data-library-view]").forEach(b=>b.setAttribute("aria-selected",String(b.dataset.libraryView===libraryView)));
  if(intro)intro.textContent=libraryView==="browse"?"Browse governed evidence already available to you. Filters change the evidence view without changing its provenance.":libraryView==="linked"?"Browse organization-controlled linked archives in place; originals stay on their authoritative storage.":"Add new evidence to the governed Library. Project context is optional and the source is chosen from the Import action.";
 }
 function setLibraryView(view){libraryView=view;ensureLibraryStructure();applyLibraryView()}
 ensureLibraryStructure();
 const libraryObserver=library?new MutationObserver(()=>{if(q("linked-storage-card")&&!q("linked-storage-card").dataset.libraryAligned){q("linked-storage-card").dataset.libraryAligned="true";applyLibraryView()}}):null;
 if(libraryObserver)libraryObserver.observe(library,{childList:true});

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
 if(uploadInput){uploadInput.hidden=true;const label=uploadInput.closest("label");if(label)label.hidden=true;}
 const folderInput=q("upload-folder-input");
 const oldFolderButton=q("upload-folder");
 if(folderInput){folderInput.hidden=true;q("import-card")?.appendChild(folderInput);}
 if(oldFolderButton)oldFolderButton.closest(".import-source-actions")?.remove();
 const sourceSummary=document.createElement("p");sourceSummary.id="import-source-summary";sourceSummary.className="import-source-summary";sourceSummary.textContent="Choose Files or Folder from Import.";
 q("import-card")?.querySelector(".form-grid")?.after(sourceSummary);
 if(uploadInput)uploadInput.addEventListener("change",()=>{const n=uploadInput.files?.length||0;sourceSummary.textContent=n?`${n} file${n===1?"":"s"} selected for governed import.`:"Choose Files or Folder from Import."});
 menu.querySelector('[data-import-source="files"]').onclick=()=>{closeImportMenu();showPage("library");setLibraryView("import");q("import-card")?.scrollIntoView({behavior:"smooth",block:"start"});uploadInput?.click()};
 menu.querySelector('[data-import-source="folder"]').onclick=()=>{closeImportMenu();showPage("library");setLibraryView("import");q("import-card")?.scrollIntoView({behavior:"smooth",block:"start"});folderInput?.click()};
 const uploadButton=q("upload-start");if(uploadButton)uploadButton.textContent="Import selected files";

 /* Home is a scientist's launch surface, not a server dashboard. Keep status
    available as secondary context while putting evidence and research work first. */
 const home=q("page-home");
 if(home&&!q("home-science-focus")){
  const top=home.querySelector(".top"),intro=document.createElement("p");
  intro.id="home-science-focus";intro.className="home-science-focus";intro.textContent="Continue evidence, observations, research records, and review work from one scientific workspace.";
  const actions=document.createElement("div");actions.id="home-primary-actions";actions.className="grid home-primary-actions";
  actions.innerHTML='<section class="card"><button type="button" data-home-target="library">Browse Library</button><p>Find governed evidence and linked archives.</p></section><section class="card"><button type="button" data-home-target="observations">Review observations</button><p>Work through field records and decisions.</p></section><section class="card"><button type="button" data-home-target="research">Research records</button><p>Continue specimens, protocols, surveys, samples, and laboratory records.</p></section><section class="card"><button type="button" data-home-target="knowledge">Knowledge &amp; AI</button><p>Review analyses and accepted knowledge.</p></section>';
  if(top){top.after(intro);intro.after(actions)}else{home.prepend(actions);home.prepend(intro)}
  actions.querySelectorAll("[data-home-target]").forEach(b=>b.onclick=()=>showPage(b.dataset.homeTarget));
  const projectCard=q("home-projects")?.closest(".card");if(projectCard?.querySelector("h2"))projectCard.querySelector("h2").textContent="Continue scientific work";
  const metrics=q("home-metrics");if(metrics){const label=document.createElement("h2");label.className="home-overview-label";label.textContent="Workspace overview";metrics.before(label)}
  const runtime=q("home-runtime"),runtimeCard=runtime?.closest(".card");
  if(runtime&&runtimeCard){
   const details=document.createElement("details");details.className="card home-system-context";const summary=document.createElement("summary");summary.textContent="System context";details.appendChild(summary);details.appendChild(runtime);runtimeCard.replaceWith(details);
  }
 }

 /* Research owns scientific records. Project portfolio, dossiers, and capacity
    already have dedicated tabs, so do not duplicate them on this page. */
 const research=q("page-research");
 if(research&&!q("research-workspace-intro")){
  const top=research.querySelector(".top"),intro=document.createElement("p");
  intro.id="research-workspace-intro";intro.className="research-workspace-intro";intro.textContent="Create and inspect scientific records here. Use Projects & Portfolio for project structure, Dossiers for assembled cases, and Capacity for planning.";
  const subnav=research.querySelector(".workspace-subnav");if(subnav)subnav.after(intro);else if(top)top.after(intro);else research.prepend(intro);
  const projectSplit=q("project-list")?.closest(".split");if(projectSplit){projectSplit.id="research-legacy-projects";projectSplit.hidden=true}
  const related=q("dossier-list")?.closest(".grid.section");if(related){related.id="research-legacy-related";related.hidden=true}
  const records=q("research-domain-list")?.closest(".card");
  if(records){records.classList.add("research-records-card");const heading=records.querySelector("h2");if(heading)heading.textContent="Research records";const note=document.createElement("p");note.className="research-context-note";note.textContent="Choose a record domain, then inspect or create records within the appropriate project context.";heading?.after(note)}
  const createDetails=records?.querySelector("details");if(createDetails){const summary=createDetails.querySelector("summary");if(summary)summary.textContent="Create research record"}
  const newProject=q("new-project");if(newProject){newProject.textContent="＋ New research record";newProject.onclick=()=>{if(!createDetails)return;createDetails.open=true;createDetails.scrollIntoView({behavior:"smooth",block:"center"});q("science-name")?.focus()}}
  const recordEditor=q("record-editor");if(recordEditor)recordEditor.hidden=true;
 }

 const active=(location.hash||"#home").slice(1);if(q(`page-${active}`))showPage(active);else showPage("home");
})();
""",
    "utf-8",
)


def patch_desktop_alignment_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
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
