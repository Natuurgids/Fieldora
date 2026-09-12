"""Keep Collections and Datasets with governed Library evidence in the web client."""

from natureai_next.server.api import ApiResponse

_LIBRARY_COLLECTIONS_PATCH = bytes(
    r"""

/* WEB-LIBRARY-COLLECTIONS-DATA-SERVICE: Library-owned collection transport boundary. */
(()=>{
 if(window.__fieldoraLibraryCollectionsWired)return;
 window.__fieldoraLibraryCollectionsWired=true;
 const moduleId="library.catalog",contractName="library.collections.service";
 const request=async(method,path,payload,revision)=>{
  const headers={"Accept":"application/json"};
  if(payload!==undefined)headers["Content-Type"]="application/json";
  if(revision!==undefined)headers["If-Match"]=String(revision);
  const response=await fetch(path,{method,headers,credentials:"same-origin",body:payload===undefined?undefined:JSON.stringify(payload)});
  const text=await response.text();
  let data={};
  try{data=text?JSON.parse(text):{};}catch(_error){data={detail:text};}
  if(!response.ok)throw new Error(data.detail||data.error||`Request failed (${response.status})`);
  return data;
 };
 const listCollections=projectId=>{
  const selected=String(projectId||"").trim();
  const suffix=selected?`?project_id=${encodeURIComponent(selected)}`:"";
  return request("GET",`/api/v1/library/collections${suffix}`);
 };
 const createCollection=(projectId,name,description)=>request(
  "POST","/api/v1/library/collections",
  {project_id:String(projectId||"").trim(),name:String(name||"").trim(),description:String(description||"").trim()||null}
 );
 const updateCollection=(collectionId,revision,changes)=>request(
  "PATCH",`/api/v1/library/collections/${encodeURIComponent(collectionId)}`,changes,revision
 );
 const linkAssets=(collectionId,revision,assetPublicIds)=>request(
  "POST",`/api/v1/library/collections/${encodeURIComponent(collectionId)}/assets`,
  {asset_public_ids:assetPublicIds},revision
 );
 const unlinkAssets=(collectionId,revision,assetPublicIds)=>request(
  "DELETE",`/api/v1/library/collections/${encodeURIComponent(collectionId)}/assets`,
  {asset_public_ids:assetPublicIds},revision
 );
 const deleteCollection=(collectionId,revision)=>request(
  "DELETE",`/api/v1/library/collections/${encodeURIComponent(collectionId)}`,undefined,revision
 );
 const implementation=Object.freeze({
  listCollections,createCollection,updateCollection,linkAssets,unlinkAssets,deleteCollection
 });
 function registerDataService(){
  const runtime=window.FieldoraModuleContracts;
  if(!runtime)return false;
  const existing=runtime.resolve?.(contractName);
  if(existing)return true;
  return runtime.register?.(contractName,moduleId,implementation)!==false;
 }
 const dataService=()=>window.FieldoraModuleContracts?.resolve?.(contractName)||implementation;
 registerDataService();
 document.addEventListener("fieldora:contracts-ready",registerDataService);

 /* WEB-038: Library-owned Collections/Datasets presentation. */
 const collections=document.getElementById("collection-list")?.closest(".card");
 const browse=document.getElementById("library-browse-panel");
 if(!collections||!browse)return;
 collections.id="library-collections-card";
 const heading=collections.querySelector("h2");
 if(heading)heading.textContent="Collections & Datasets";
 const intro=document.createElement("p");
 intro.className="muted";
 intro.textContent="Organize governed Library evidence without changing its provenance or source ownership.";
 if(heading)heading.after(intro);
 browse.appendChild(collections);

 const parity=document.createElement("section");
 parity.id="library-collections-parity";
 parity.innerHTML=`
  <div class="row" style="gap:.5rem;flex-wrap:wrap;align-items:end">
   <label>Project ID<br><input id="library-collection-project" placeholder="project public ID"></label>
   <label>Name<br><input id="library-collection-name" placeholder="Collection name"></label>
   <label>Description<br><input id="library-collection-description" placeholder="Optional description"></label>
   <button id="library-collection-create" type="button">Create collection</button>
   <button id="library-collection-refresh" type="button">Refresh</button>
  </div>
  <p class="muted">Membership is reference-only. Removing evidence from a collection, or deleting the collection, never deletes the governed evidence or its provenance.</p>
  <div id="library-collection-parity-status" class="muted" role="status"></div>
  <div id="library-collection-parity-list"></div>`;
 collections.appendChild(parity);

 const project=parity.querySelector("#library-collection-project");
 const name=parity.querySelector("#library-collection-name");
 const description=parity.querySelector("#library-collection-description");
 const status=parity.querySelector("#library-collection-parity-status");
 const list=parity.querySelector("#library-collection-parity-list");
 const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
 const ids=value=>String(value||"").split(/[\s,]+/).map(item=>item.trim()).filter(Boolean);
 const setStatus=(message,error=false)=>{status.textContent=message||"";status.dataset.error=error?"true":"false";};
 const render=items=>{
  if(!items.length){list.innerHTML='<p class="muted">No governed Library collections yet.</p>';return;}
  list.innerHTML=items.map(item=>`
   <article class="card" data-library-collection-id="${esc(item.id)}" data-revision="${esc(item.revision)}" style="margin-top:.75rem">
    <strong>${esc(item.name)}</strong>
    <span class="muted"> · ${esc(item.project_id)} · ${Number(item.asset_public_ids?.length||0)} member(s)</span>
    ${item.description?`<p>${esc(item.description)}</p>`:""}
    <div class="row" style="gap:.4rem;flex-wrap:wrap">
     <button type="button" data-action="edit">Edit</button>
     <button type="button" data-action="link">Add evidence</button>
     <button type="button" data-action="unlink">Remove from collection</button>
     <button type="button" data-action="delete">Delete collection</button>
    </div>
   </article>`).join("");
 };
 const load=async()=>{
  try{
   setStatus("Loading collections…");
   const data=await dataService().listCollections(project.value.trim());
   render(Array.isArray(data.items)?data.items:[]);
   setStatus(`${Array.isArray(data.items)?data.items.length:0} collection(s) loaded.`);
  }catch(error){setStatus(error.message,true);}
 };
 parity.querySelector("#library-collection-create").addEventListener("click",async()=>{
  try{
   const projectId=project.value.trim(), collectionName=name.value.trim();
   if(!projectId||!collectionName)throw new Error("Project ID and collection name are required.");
   setStatus("Creating collection…");
   await dataService().createCollection(projectId,collectionName,description.value.trim());
   name.value="";description.value="";
   await load();
  }catch(error){setStatus(error.message,true);}
 });
 parity.querySelector("#library-collection-refresh").addEventListener("click",load);
 list.addEventListener("click",async event=>{
  const button=event.target.closest("button[data-action]");
  const card=button?.closest("[data-library-collection-id]");
  if(!button||!card)return;
  const collectionId=card.dataset.libraryCollectionId;
  const revision=Number(card.dataset.revision);
  const action=button.dataset.action;
  try{
   if(action==="edit"){
    const currentName=card.querySelector("strong")?.textContent||"";
    const nextName=window.prompt("Collection name",currentName);
    if(nextName===null)return;
    const nextDescription=window.prompt("Description (blank removes it)",card.querySelector("p")?.textContent||"");
    if(nextDescription===null)return;
    await dataService().updateCollection(collectionId,revision,{name:nextName,description:nextDescription||null});
   }else if(action==="link"||action==="unlink"){
    const promptText=action==="link"?"Evidence public IDs to add (comma or space separated)":"Evidence public IDs to remove from this collection only";
    const entered=window.prompt(promptText,"");
    if(entered===null)return;
    const assetIds=ids(entered);
    if(!assetIds.length)throw new Error("Enter at least one evidence public ID.");
    if(action==="link")await dataService().linkAssets(collectionId,revision,assetIds);
    else await dataService().unlinkAssets(collectionId,revision,assetIds);
   }else if(action==="delete"){
    if(!window.confirm("Delete this collection? Governed evidence and provenance will not be deleted."))return;
    await dataService().deleteCollection(collectionId,revision);
   }
   await load();
  }catch(error){setStatus(error.message,true);}
 });
 load();
})();
""",
    "utf-8",
)


def patch_library_collections_web_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    if (
        target.partition("?")[0] != "/app.js"
        or response.status != 200
        or _LIBRARY_COLLECTIONS_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LIBRARY_COLLECTIONS_PATCH,
        response.content_type,
        response.headers,
    )
