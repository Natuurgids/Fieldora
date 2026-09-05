"""Actionable optimistic-concurrency conflict UX for governed browser mutations."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_OPTIMISTIC_CONCURRENCY_PATCH = bytes(
    r"""

/* WEB-050: preserve governed revision-conflict context for reload/compare UX. */
(()=>{
 if(window.__fieldoraOptimisticConcurrency)return;
 window.__fieldoraOptimisticConcurrency=true;
 const nativeFetch=window.fetch.bind(window);
 let capturedConflict=null;
 const safeJson=value=>{
  try{return JSON.parse(value||"{}")}catch(_error){return {}}
 };
 const escapeConflict=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const requestPath=input=>{
  try{return new URL(typeof input==="string"?input:input.url,window.location.href).pathname}catch(_error){return ""}
 };
 window.fetch=async function(input,init){
  const response=await nativeFetch(input,init);
  if(response.status===409){
   try{
    const payload=await response.clone().json();
    if(payload?.error==="revision_conflict")capturedConflict={path:requestPath(input),payload};
   }catch(_error){}
  }
  return response;
 };

 const style=document.createElement("style");
 style.textContent=`
  #revision-conflict-dialog{max-width:min(860px,92vw);border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--text);padding:0;box-shadow:0 24px 70px #0009}
  #revision-conflict-dialog::backdrop{background:#071012bb}
  .revision-conflict-body{padding:18px}.revision-conflict-body h2{margin-top:0}.revision-conflict-body>p{color:var(--muted)}
  .revision-conflict-compare{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
  .revision-conflict-compare section{min-width:0;border:1px solid var(--line);border-radius:7px;padding:10px;background:#111a1d}
  .revision-conflict-compare h3{margin:0 0 8px;font-size:13px}.revision-conflict-compare pre{margin:0;max-height:300px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
  .revision-conflict-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
  @media(max-width:700px){.revision-conflict-compare{grid-template-columns:1fr}}
 `;
 document.head.appendChild(style);
 const dialog=document.createElement("dialog");
 dialog.id="revision-conflict-dialog";
 dialog.innerHTML='<div class="revision-conflict-body"><h2>Changes conflict</h2><p>Another update was saved after this record was opened. Compare your attempted values with the current governed record before continuing.</p><div class="revision-conflict-compare"><section><h3>Your attempted values</h3><pre id="revision-conflict-local"></pre></section><section><h3>Current server values</h3><pre id="revision-conflict-current"></pre></section></div><div class="revision-conflict-actions"><button id="revision-conflict-keep" type="button">Keep editing</button><button id="revision-conflict-reload" class="primary" type="button">Reload latest</button></div></div>';
 document.body.appendChild(dialog);
 const localNode=document.getElementById("revision-conflict-local");
 const currentNode=document.getElementById("revision-conflict-current");
 const keepButton=document.getElementById("revision-conflict-keep");
 const reloadButton=document.getElementById("revision-conflict-reload");
 keepButton.onclick=()=>dialog.close();

 const previousApi=api;
 async function reloadProjects(current){
  if(!current?.id)return;
  try{
   const result=await previousApi("/api/v1/projects?limit=50",{purpose:"research"});
   projects=result.items||[];
   if(typeof projectOptions==="function")projectOptions();
   if(typeof loadPortfolio==="function")await loadPortfolio();
   if(selectedProject===current.id&&typeof openProject==="function")openProject(current.id);
  }catch(_error){}
 }
 api=async function(path,options={}){
  try{return await previousApi(path,options)}catch(error){
   const conflict=capturedConflict;
   capturedConflict=null;
   if((error?.code||error?.message)!=="revision_conflict"||!conflict||conflict.path!==requestPath(path))throw error;
   const attempted=safeJson(options.body);
   const current=conflict.payload?.current||null;
   localNode.textContent=JSON.stringify(attempted,null,2);
   currentNode.textContent=JSON.stringify(current,null,2);
   reloadButton.onclick=async()=>{reloadButton.disabled=true;await reloadProjects(current);reloadButton.disabled=false;dialog.close()};
   if(typeof dialog.showModal==="function")dialog.showModal();else dialog.setAttribute("open","");
   const actionable=new Error("This record changed on the server. Compare your changes or reload the latest version.");
   actionable.name="RevisionConflictError";
   actionable.current=current;
   actionable.attempted=attempted;
   throw actionable;
  }
 };
})();
""",
    "utf-8",
)


class OptimisticConcurrencyWebApiMixin:
    """Append revision-conflict presentation after established browser API wrappers."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if (
            method != "GET"
            or urlsplit(target).path != "/app.js"
            or response.status != 200
            or _OPTIMISTIC_CONCURRENCY_PATCH in response.body
        ):
            return response
        return ApiResponse(
            response.status,
            response.body + _OPTIMISTIC_CONCURRENCY_PATCH,
            response.content_type,
            response.headers,
        )
