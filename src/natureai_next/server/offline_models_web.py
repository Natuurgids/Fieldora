"""Managed-web controls for registering verified offline model artifacts."""

from natureai_next.server.api import ApiResponse

_OFFLINE_MODELS_WEB_PATCH = bytes(
    r"""

/* Fieldora offline models: reconcile verified local artifacts with governed ai-models. */
(()=>{
 if(window.__fieldoraOfflineModelsWired)return;
 window.__fieldoraOfflineModelsWired=true;
 const administrationCollections=new Set([
  "ai-providers","ai-models","mcp-servers","connectors","reference-values"
 ]);
 const baseApi=api;
 api=async function(path,options={}){
  const route=String(path||"").split("?",1)[0].replace(/^\/api\/v1\//,"");
  const collection=route.split("/",1)[0];
  if(administrationCollections.has(collection)&&!options.purpose){
   options={...options,purpose:"administration"};
  }
  return baseApi(path,options);
 };
 const page=document.getElementById("page-aiadmin");
 if(!page)return;
 const section=document.createElement("section");
 section.className="card section";
 section.id="offline-model-artifacts";
 section.innerHTML=`
  <h2>Installed offline model artifacts</h2>
  <p class="muted">Verified model bundles installed on this Fieldora node. Registration is explicit and stores only an opaque artifact ID; server filesystem paths are never shown here.</p>
  <div id="offline-model-list" class="list"></div>
  <p id="offline-model-status" class="status"></p>`;
 const modelList=document.getElementById("model-list");
 const modelCard=modelList?.closest(".card");
 if(modelCard)modelCard.insertAdjacentElement("afterend",section);
 else page.appendChild(section);
 let installedModels=new Map();
 const trustLabel=item=>{
  if(item.malware_scan?.result==="clean"){
   const scanner=item.malware_scan.scanner||"approved scanner";
   return `Signed + clean scanned · ${scanner}`;
  }
  if(item.manifest_signature==="ed25519")return "Signed manifest";
  return "Unsigned local bundle";
 };
 const renderOfflineModels=async()=>{
  const list=document.getElementById("offline-model-list");
  const statusNode=document.getElementById("offline-model-status");
  if(!list||!statusNode)return;
  try{
   const [installed,governed]=await Promise.all([
    api("/api/v1/ai-models/installed",{purpose:"administration"}),
    fetchItems("ai-models")
   ]);
   const registered=new Set((governed||[]).map(item=>item.id));
   installedModels=new Map((installed.items||[]).map(item=>[item.id,item]));
   list.innerHTML=(installed.items||[]).map(item=>{
    const exists=registered.has(item.id);
    const size=(Number(item.artifact_total_bytes||0)/1073741824).toFixed(2);
    const trust=trustLabel(item);
    return `<div class="row" data-offline-model="${esc(item.id)}"><div><strong>${esc(item.name||item.model_id)}</strong><br><span class="muted">${esc(item.version)} · ${esc((item.formats||[]).join(", "))}<br>${esc(trust)}</span></div><span>${size} GiB</span><span>${esc(item.license_id||"unspecified")}</span><button data-register-offline-model="${esc(item.id)}" ${exists?"disabled":""}>${exists?"Registered":"Register & enable"}</button></div>`;
   }).join("")||'<div class="empty">No verified offline model artifacts are installed.</div>';
   statusNode.textContent="";
  }catch(error){
   const message=String(error?.message||error);
   if(message.includes("offline_model_store_unavailable")){
    list.innerHTML='<div class="empty">Offline model storage is not configured on this server.</div>';
    statusNode.textContent="";
   }else{
    list.innerHTML='<div class="empty">Installed model discovery is unavailable.</div>';
    statusNode.textContent=message;
   }
  }
 };
 section.addEventListener("click",async event=>{
  const button=event.target.closest("[data-register-offline-model]");
  if(!button)return;
  const item=installedModels.get(button.dataset.registerOfflineModel);
  if(!item)return;
  button.disabled=true;
  const statusNode=document.getElementById("offline-model-status");
  try{
   await api("/api/v1/ai-models",{
    method:"POST",purpose:"administration",
    body:JSON.stringify({...item,enabled:true,status:"active"})
   });
   if(statusNode)statusNode.textContent=`Registered ${item.name||item.model_id} ${item.version}.`;
   await loadAIAdministration();
  }catch(error){
   button.disabled=false;
   if(statusNode)statusNode.textContent=String(error?.message||error);
  }
 });
 const baseLoadAIAdministration=loadAIAdministration;
 loadAIAdministration=async function(){
  await baseLoadAIAdministration();
  await renderOfflineModels();
 };
 const refresh=document.getElementById("aiadmin-refresh");
 if(refresh)refresh.onclick=()=>loadAIAdministration();
})();
""",
    "utf-8",
)


def patch_offline_models_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _OFFLINE_MODELS_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _OFFLINE_MODELS_WEB_PATCH,
        response.content_type,
        response.headers,
    )
