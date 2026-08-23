"""Functional browser compatibility additions for the managed Fieldora web UI."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_BROWSER_FUNCTIONALITY_PATCH = bytes(
    r"""

/* Fieldora browser functionality: recursive intake, project creation and media preview. */
(()=>{
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

 /* Mark browser requests so an OIDC bearer session can also establish the
    Secure/HttpOnly same-origin media session cookie. */
 const baseApi=api;
 api=async function(path,options={}){
  options.headers={...(options.headers||{}),"X-Fieldora-Web-Session":"1"};
  return baseApi(path,options);
 };

 const style=document.createElement("style");
 style.textContent=`
  .media-native{width:100%;max-height:260px;border-radius:9px;background:#0b1113;object-fit:contain}
  audio.media-native{min-height:46px}
  .view-indicator{margin:10px 0 0;color:var(--muted);font-size:13px}
  .import-source-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:10px}
 `;
 document.head.appendChild(style);

 function mediaSource(m){return m.download_url||`/api/v1/media/${encodeURIComponent(m.media_id)}`}
 function mediaPreview(m,detailed=false){
  const src=html(mediaSource(m)),type=String(m.mime_type||"");
  if(type.startsWith("image/"))return `<img class="media-native" src="${src}" loading="lazy" alt="Governed evidence ${html(m.media_id)}">`;
  if(type.startsWith("audio/"))return `<audio class="media-native" controls preload="metadata" src="${src}"></audio>`;
  if(type.startsWith("video/"))return `<video class="media-native" controls preload="metadata" src="${src}"></video>`;
  return `<div class="thumb">▤</div>${detailed?'<p class="muted">Preview is not available for this document type.</p>':''}`;
 }

 /* Replace icon-only gallery rendering with governed native media elements.
    The browser cookie authenticates these same-origin Range requests. */
 renderMedia=function(){
  let shown=media.filter(m=>mediaFilter==="all"||String(m.mime_type||"").startsWith(mediaFilter+"/"));
  const text=(document.querySelector("#page-library .global-search")?.value||"").toLowerCase();
  shown=shown.filter(m=>JSON.stringify(m).toLowerCase().includes(text));
  const labels={all:"All media",image:"Photos",audio:"Sounds",video:"Videos",application:"Documents"};
  const target=byId("media-grid");
  target.dataset.renderedView=mediaFilter;
  cards("media-grid",shown,m=>`<article class="card" data-media="${html(m.media_id)}">${mediaPreview(m)}<p><strong>${html(m.mime_type)}</strong></p><p class="muted">${(Number(m.size_bytes||0)/1048576).toFixed(2)} MB · ${m.project_id?`project ${html(m.project_id)}`:"General Library"}</p></article>`,`No ${labels[mediaFilter]||"media"} in this view.`);
  setIndicator("library-view-indicator",`${labels[mediaFilter]||"Media"} · ${shown.length} item${shown.length===1?"":"s"}`);
 };
 byId("media-grid").onclick=e=>{
  const card=e.target.closest("[data-media]");if(!card)return;
  const m=media.find(x=>x.media_id===card.dataset.media);if(!m)return;
  byId("media-detail").innerHTML=`${mediaPreview(m,true)}<h3>${html(m.mime_type)}</h3><p>Media ID<br><code>${html(m.media_id)}</code></p><p>${m.project_id?`Project ${html(m.project_id)}`:"General Library"} · ${(Number(m.size_bytes||0)/1048576).toFixed(2)} MB</p><p>SHA-256<br><code>${html(m.sha256)}</code></p><button id="media-download">Download governed original</button>`;
  byId("media-download").onclick=()=>download(mediaSource(m),`fieldora-media-${m.media_id}`);
 };

 async function digestFile(file){
  const bytes=await file.arrayBuffer();
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return {bytes,hash:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("")};
 }
 async function uploadOne(file,project,index,total){
  status("upload-status",`Checksum ${index}/${total}: ${file.name}`);
  const {bytes,hash}=await digestFile(file);
  const begun=await api("/api/v1/uploads",{method:"POST",body:JSON.stringify({project_id:project,filename:file.name,mime_type:file.type||"application/octet-stream",size_bytes:file.size,sha256:hash})});
  let result=null;
  for(let start=0;start<file.size;start+=4*1024*1024){
   const end=Math.min(file.size,start+4*1024*1024);
   result=await api(`/api/v1/uploads/${begun.upload_id}`,{method:"PUT",headers:{"Content-Range":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});
   status("upload-status",`File ${index}/${total} · ${Math.round(end/file.size*100)}% · ${file.name}`);
  }
  return result;
 }
 async function uploadSelectedFiles(){
  const files=[...(byId("upload-file")?.files||[])],project=byId("upload-project")?.value||"";
  if(!files.length)return status("upload-status","Choose one or more files, or choose a folder.",true);
  try{
   for(let i=0;i<files.length;i++)await uploadOne(files[i],project,i+1,files.length);
   status("upload-status",`${files.length} file${files.length===1?"":"s"} verified · ${project?"project-linked":"General Library"}`);
   await loadMedia();
  }catch(e){status("upload-status",e.message,true)}
 }
 async function uploadFolder(files){
  const project=byId("upload-project")?.value||"";
  if(!files.length)return;
  try{
   status("upload-status",`Preparing folder · ${files.length} files`);
   const created=await api("/api/v1/staged-submissions",{method:"POST",body:JSON.stringify({project_id:project,contract_id:"",publication_policy:"review",expected_files:files.length})});
   const sid=created.submission.submission_id;
   for(let i=0;i<files.length;i++){
    const file=files[i],relative=file.webkitRelativePath||file.name,{bytes,hash}=await digestFile(file);
    status("upload-status",`Folder ${i+1}/${files.length} · ${relative}`);
    const begun=await api(`/api/v1/staged-submissions/${sid}/files`,{method:"POST",body:JSON.stringify({filename:file.name,relative_path:relative,mime_type:file.type||"application/octet-stream",size_bytes:file.size,sha256:hash})});
    for(let start=0;start<file.size;start+=4*1024*1024){
     const end=Math.min(file.size,start+4*1024*1024);
     await api(`/api/v1/staged-files/${begun.staged_file_id}`,{method:"PUT",headers:{"Content-Range":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});
    }
   }
   await api(`/api/v1/staged-submissions/${sid}/seal`,{method:"POST",body:"{}"});
   await api(`/api/v1/staged-submissions/${sid}/process`,{method:"POST",body:"{}"});
   status("upload-status",`Folder accepted · ${files.length} files · paths preserved · submission ${sid}`);
   await loadMedia();
  }catch(e){status("upload-status",e.message,true)}
 }
 const uploadInput=byId("upload-file");
 if(uploadInput){
  uploadInput.multiple=true;
  const label=uploadInput.closest("label");if(label&&label.firstChild)label.firstChild.textContent="Files";
 }
 const uploadButton=byId("upload-start");if(uploadButton)uploadButton.onclick=uploadSelectedFiles;
 const importCard=byId("import-card");
 if(importCard&&!byId("upload-folder")){
  const row=document.createElement("div");row.className="import-source-actions";
  row.innerHTML='<button id="upload-folder" type="button">Choose folder and subfolders</button><input id="upload-folder-input" type="file" multiple hidden><span class="muted">Folder import preserves relative paths.</span>';
  importCard.querySelector(".actions")?.after(row);
  const folderInput=byId("upload-folder-input");
  folderInput.setAttribute("webkitdirectory","");folderInput.setAttribute("directory","");
  byId("upload-folder").onclick=()=>folderInput.click();
  folderInput.onchange=()=>uploadFolder([...folderInput.files]);
 }

 /* Project creation belongs in Projects & Portfolio as well as Research. */
 const projectsPage=byId("page-projects");
 if(projectsPage&&!byId("portfolio-new-project")){
  const top=projectsPage.querySelector(".top"),button=document.createElement("button");
  button.id="portfolio-new-project";button.className="primary";button.textContent="＋ Add project";top?.appendChild(button);
  const editor=document.createElement("section");editor.id="portfolio-project-editor";editor.className="card section";editor.hidden=true;
  editor.innerHTML='<h2>Add project</h2><div class="form-grid"><label>Name<input id="portfolio-project-name"></label><label>Status<select id="portfolio-project-status"><option value="active">active</option><option value="planned">planned</option></select></label></div><label class="section">Description<textarea id="portfolio-project-description"></textarea></label><div class="actions section"><button id="portfolio-project-save" class="primary">Create project</button><button id="portfolio-project-cancel">Cancel</button></div><p id="portfolio-project-status-message" class="status"></p>';
  const first=projectsPage.querySelector(".card");if(first)first.before(editor);else projectsPage.appendChild(editor);
  button.onclick=()=>{editor.hidden=false;byId("portfolio-project-name").focus()};
  byId("portfolio-project-cancel").onclick=()=>{editor.hidden=true};
  byId("portfolio-project-save").onclick=async()=>{
   const name=byId("portfolio-project-name").value.trim();if(!name)return status("portfolio-project-status-message","Project name is required.",true);
   try{
    const record={id:crypto.randomUUID(),name,description:byId("portfolio-project-description").value.trim(),status:byId("portfolio-project-status").value,owner_id:me?.identity_id||""};
    await api("/api/v1/projects",{method:"POST",purpose:"research",body:JSON.stringify(record)});
    projects=(await api("/api/v1/projects")).items||[];projectOptions();editor.hidden=true;await loadPortfolio();
   }catch(e){status("portfolio-project-status-message",e.message,true)}
  };
 }

 function setIndicator(id,text){
  let node=byId(id);if(!node){node=document.createElement("div");node.id=id;node.className="view-indicator";}
  node.textContent=text;
  if(!node.isConnected){
   const page=id.startsWith("library")?byId("page-library"):id.startsWith("portfolio")?byId("page-projects"):id.startsWith("research")?byId("page-research"):id.startsWith("operations")?byId("page-operations"):id.startsWith("knowledge")?byId("page-knowledge"):id.startsWith("observation")?byId("page-observations"):null;
   page?.querySelector(".tabs")?.after(node);
  }
 }
 const portfolioLabels={hierarchy:"Hierarchy",kanban:"Kanban",grid:"Grid",gantt:"Gantt",workload:"Workload",budget:"Budget"};
 document.querySelectorAll("[data-portfolio-view]").forEach(b=>b.addEventListener("click",()=>setIndicator("portfolio-view-indicator",`${portfolioLabels[b.dataset.portfolioView]||b.dataset.portfolioView} view`)));
 document.querySelectorAll("[data-research-domain]").forEach(b=>b.addEventListener("click",()=>setIndicator("research-view-indicator",`${b.textContent.trim()} view`)));
 document.querySelectorAll("[data-operations-domain]").forEach(b=>b.addEventListener("click",()=>setIndicator("operations-view-indicator",`${b.textContent.trim()} view`)));
 document.querySelectorAll("[data-knowledge-view]").forEach(b=>b.addEventListener("click",()=>setIndicator("knowledge-view-indicator",`${b.textContent.trim()} view`)));
 document.querySelectorAll("[data-observation-filter]").forEach(b=>b.addEventListener("click",()=>setIndicator("observation-view-indicator",`${b.textContent.trim()} view`)));
 setIndicator("portfolio-view-indicator",`${portfolioLabels[portfolioView]||"Hierarchy"} view`);
 setIndicator("research-view-indicator","Specimens view");
 setIndicator("operations-view-indicator","Assets view");
 setIndicator("knowledge-view-indicator","Review queue view");
 setIndicator("observation-view-indicator","All records view");
})();
""",
    "utf-8",
)


def patch_browser_functionality_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _BROWSER_FUNCTIONALITY_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _BROWSER_FUNCTIONALITY_PATCH,
        response.content_type,
        response.headers,
    )
