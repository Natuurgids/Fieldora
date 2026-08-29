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
   status("upload-status",`Validating folder · ${validated}/${total} · ${submission.state||"scanning"}`);
   if(["validated","validated_with_rejections","processing","ready_to_publish","published"].includes(submission.state))return current;
   if(["failed","rejected"].includes(submission.state))throw new Error(`Folder validation failed: ${submission.state}`);
   await sleep(500);
  }
  throw new Error("Folder validation is still running; the submission remains queued and can continue in the background.");
 }
 async function waitForProcessing(submissionId,total){
  for(let attempt=0;attempt<600;attempt++){
   const current=await api(`/api/v1/staged-submissions/${submissionId}`);
   const submission=current.submission||{},files=current.files||[];
   const complete=files.filter(f=>["published","rejected"].includes(f.state)).length;
   status("upload-status",`Publishing folder · ${complete}/${total} · ${submission.state||"processing"}`);
   if(submission.state==="published")return current;
   if(submission.state==="failed")throw new Error("Folder processing failed.");
   await sleep(500);
  }
  throw new Error("Folder publication is still running; the submission remains queued and can continue in the background.");
 }
 async function governedFolderUpload(files){
  const project=byId("upload-project")?.value||"";
  if(!files.length)return;
  try{
   status("upload-status",`Preparing folder · ${files.length} files`);
   const created=await api("/api/v1/staged-submissions",{method:"POST",body:JSON.stringify({project_id:project,contract_id:"",publication_policy:"review",expected_files:files.length})});
   const sid=created.submission.submission_id;
   for(let i=0;i<files.length;i++){
    const file=files[i],relative=file.webkitRelativePath||file.name,{bytes,hash}=await digestFileForFolder(file);
    status("upload-status",`Folder ${i+1}/${files.length} · ${relative}`);
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
   await waitForProcessing(sid,files.length);
   status("upload-status",`Folder imported · ${files.length-rejected.length} published · ${rejected.length} rejected · submission ${sid}` , rejected.length>0);
   await loadMedia();
  }catch(e){status("upload-status",e.message||String(e),true)}
 }
 const folderInput=byId("upload-folder-input");
 if(folderInput){folderInput.onchange=()=>governedFolderUpload([...folderInput.files]);}
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
