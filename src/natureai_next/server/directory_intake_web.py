"""Browser folder-intake sequencing over the staged ingestion state machine."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_DIRECTORY_INTAKE_PATCH = bytes(
    r"""

/* Fieldora folder intake: upload -> seal -> validate workers -> process/publish workers. */
(()=>{
 const byId=id=>document.getElementById(id);
 const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const BACKGROUND_IMPORTS_KEY="fieldora.background-folder-imports.v1";
 const TERMINAL_IMPORT_STATES=new Set(["published","failed","rejected"]);
 class BackgroundImportContinues extends Error{
  constructor(message){super(message);this.name="BackgroundImportContinues";this.background=true;}
 }
 function readBackgroundImports(){
  try{
   const value=JSON.parse(localStorage.getItem(BACKGROUND_IMPORTS_KEY)||"[]");
   if(!Array.isArray(value))return [];
   return value.filter(item=>item&&typeof item.submission_id==="string")
    .slice(0,20)
    .map(item=>({
     submission_id:item.submission_id,
     state:String(item.state||"queued"),
     expected_files:Number(item.expected_files||0),
     completed_files:Number(item.completed_files||0),
     updated_at:Number(item.updated_at||0),
    }));
  }catch(_error){return [];}
 }
 function writeBackgroundImports(records){
  localStorage.setItem(BACKGROUND_IMPORTS_KEY,JSON.stringify(records.slice(0,20)));
 }
 function rememberBackgroundImport(submissionId,patch={}){
  const records=readBackgroundImports();
  const existing=records.find(item=>item.submission_id===submissionId)||{
   submission_id:submissionId,state:"queued",expected_files:0,completed_files:0,updated_at:0,
  };
  Object.assign(existing,patch,{submission_id:submissionId,updated_at:Date.now()});
  const next=[existing,...records.filter(item=>item.submission_id!==submissionId)].slice(0,20);
  writeBackgroundImports(next);
  renderBackgroundImports();
  return existing;
 }
 function removeBackgroundImport(submissionId){
  writeBackgroundImports(readBackgroundImports().filter(item=>item.submission_id!==submissionId));
  renderBackgroundImports();
 }
 function summarizeSubmission(current,total=0){
  const submission=current?.submission||{},files=current?.files||[];
  const complete=files.filter(file=>["published","rejected","failed"].includes(file.state)).length;
  return {
   state:String(submission.state||"queued"),
   expected_files:Number(submission.expected_files||total||files.length||0),
   completed_files:complete,
  };
 }
 async function refreshBackgroundImport(submissionId,{quiet=false}={}){
  try{
   const current=await api(`/api/v1/staged-submissions/${encodeURIComponent(submissionId)}`);
   const summary=summarizeSubmission(current);
   rememberBackgroundImport(submissionId,summary);
   if(summary.state==="published"){
    if(!quiet)status("upload-status",`Background folder import published · submission ${submissionId}`);
    if(typeof loadMedia==="function")await loadMedia();
   }else if(["failed","rejected"].includes(summary.state)){
    if(!quiet)status("upload-status",`Background folder import ${summary.state} · submission ${submissionId}`,true);
   }else if(!quiet){
    status("upload-status",`Background folder import · ${summary.completed_files}/${summary.expected_files} · ${summary.state} · submission ${submissionId}`);
   }
   return current;
  }catch(error){
   if(!quiet)status("upload-status",error.message||String(error),true);
   throw error;
  }
 }
 function ensureBackgroundImportsPanel(){
  let panel=byId("folder-background-imports");
  if(panel)return panel;
  const uploadStatus=byId("upload-status");
  if(!uploadStatus)return null;
  panel=document.createElement("section");
  panel.id="folder-background-imports";
  panel.className="card";
  panel.style.marginTop="16px";
  const title=document.createElement("h3");
  title.textContent="Background imports";
  const description=document.createElement("p");
  description.className="muted";
  description.textContent="Durable folder submissions continue after this page stops waiting. Refresh a submission to reconcile its current governed state.";
  const list=document.createElement("div");
  list.id="folder-background-import-list";
  panel.append(title,description,list);
  const advanced=uploadStatus.parentElement?.querySelector("details");
  if(advanced)advanced.before(panel);else uploadStatus.after(panel);
  return panel;
 }
 function renderBackgroundImports(){
  const panel=ensureBackgroundImportsPanel();
  if(!panel)return;
  const list=byId("folder-background-import-list");
  if(!list)return;
  list.replaceChildren();
  const records=readBackgroundImports();
  panel.hidden=records.length===0;
  records.forEach(record=>{
   const row=document.createElement("div");
   row.className="row";
   row.style.alignItems="center";
   row.style.gap="10px";
   row.style.marginTop="8px";
   const summary=document.createElement("span");
   summary.style.flex="1";
   summary.textContent=`Submission ${record.submission_id} · ${record.state} · ${record.completed_files}/${record.expected_files}`;
   const refresh=document.createElement("button");
   refresh.type="button";
   refresh.textContent="Refresh";
   refresh.addEventListener("click",()=>refreshBackgroundImport(record.submission_id));
   row.append(summary,refresh);
   if(TERMINAL_IMPORT_STATES.has(record.state)){
    const dismiss=document.createElement("button");
    dismiss.type="button";
    dismiss.textContent="Dismiss";
    dismiss.addEventListener("click",()=>removeBackgroundImport(record.submission_id));
    row.appendChild(dismiss);
   }
   list.appendChild(row);
  });
 }
 async function digestFileForFolder(file){
  const bytes=await file.arrayBuffer();
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return {bytes,hash:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("")};
 }
 async function waitForValidation(submissionId,total){
  for(let attempt=0;attempt<600;attempt++){
   const current=await api(`/api/v1/staged-submissions/${submissionId}`);
   const submission=current.submission||{},files=current.files||[];
   const validated=files.filter(f=>["validated","rejected","processing","processed","published"].includes(f.state)).length;
   rememberBackgroundImport(submissionId,summarizeSubmission(current,total));
   status("upload-status",`Validating folder · ${validated}/${total} · ${submission.state||"scanning"} · submission ${submissionId}`);
   if(["validated","validated_with_rejections","processing","ready_to_publish","published"].includes(submission.state))return current;
   if(["failed","rejected"].includes(submission.state))throw new Error(`Folder validation failed: ${submission.state}`);
   await sleep(500);
  }
  throw new BackgroundImportContinues(`Folder validation continues in the background · submission ${submissionId}`);
 }
 async function waitForProcessing(submissionId,total){
  for(let attempt=0;attempt<600;attempt++){
   const current=await api(`/api/v1/staged-submissions/${submissionId}`);
   const submission=current.submission||{},files=current.files||[];
   const complete=files.filter(f=>["published","rejected"].includes(f.state)).length;
   rememberBackgroundImport(submissionId,summarizeSubmission(current,total));
   status("upload-status",`Publishing folder · ${complete}/${total} · ${submission.state||"processing"} · submission ${submissionId}`);
   if(submission.state==="published")return current;
   if(submission.state==="failed")throw new Error("Folder processing failed.");
   await sleep(500);
  }
  throw new BackgroundImportContinues(`Folder publication continues in the background · submission ${submissionId}`);
 }
 async function governedFolderUpload(files){
  const project=byId("upload-project")?.value||"";
  if(!files.length)return;
  let sid="";
  try{
   status("upload-status",`Preparing folder · ${files.length} files`);
   const created=await api("/api/v1/staged-submissions",{method:"POST",body:JSON.stringify({project_id:project,contract_id:"",publication_policy:"review",expected_files:files.length})});
   sid=created.submission.submission_id;
   rememberBackgroundImport(sid,{state:created.submission.state||"uploading",expected_files:files.length,completed_files:0});
   for(let i=0;i<files.length;i++){
    const file=files[i],relative=file.webkitRelativePath||file.name,{bytes,hash}=await digestFileForFolder(file);
    status("upload-status",`Folder ${i+1}/${files.length} · ${relative} · submission ${sid}`);
    const begun=await api(`/api/v1/staged-submissions/${sid}/files`,{method:"POST",body:JSON.stringify({filename:file.name,relative_path:relative,mime_type:file.type||"application/octet-stream",size_bytes:file.size,sha256:hash})});
    for(let start=0;start<file.size;start+=4*1024*1024){
     const end=Math.min(file.size,start+4*1024*1024);
     await api(`/api/v1/staged-files/${begun.staged_file_id}`,{method:"PUT",headers:{"Content-Range":`bytes ${start}-${end-1}/${file.size}`},body:bytes.slice(start,end)});
    }
   }
   await api(`/api/v1/staged-submissions/${sid}/seal`,{method:"POST",body:"{}"});
   const validated=await waitForValidation(sid,files.length);
   const rejected=(validated.files||[]).filter(f=>f.state==="rejected");
   if(["validated","validated_with_rejections"].includes(validated.submission?.state||"")){
    await api(`/api/v1/staged-submissions/${sid}/process`,{method:"POST",body:"{}"});
   }
   const published=await waitForProcessing(sid,files.length);
   rememberBackgroundImport(sid,summarizeSubmission(published,files.length));
   status("upload-status",`Folder imported · ${files.length-rejected.length} published · ${rejected.length} rejected · submission ${sid}` , rejected.length>0);
   await loadMedia();
  }catch(e){
   if(sid&&e?.background){
    rememberBackgroundImport(sid,{state:"running",expected_files:files.length});
    status("upload-status",e.message||String(e),false);
   }else{
    if(sid)rememberBackgroundImport(sid,{state:"failed",expected_files:files.length});
    status("upload-status",e.message||String(e),true);
   }
  }
 }
 const folderInput=byId("upload-folder-input");
 if(folderInput){folderInput.onchange=()=>governedFolderUpload([...folderInput.files]);}
 renderBackgroundImports();
 readBackgroundImports().filter(item=>!TERMINAL_IMPORT_STATES.has(item.state)).forEach(item=>{
  refreshBackgroundImport(item.submission_id,{quiet:true}).catch(()=>{});
 });
})();
""",
    "utf-8",
)


def patch_directory_intake_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _DIRECTORY_INTAKE_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _DIRECTORY_INTAKE_PATCH,
        response.content_type,
        response.headers,
    )
