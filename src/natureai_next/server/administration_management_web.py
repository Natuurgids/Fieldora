"""Simple organisation-management controls inside the Administration workspace."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ADMINISTRATION_MANAGEMENT_WEB_PATCH = bytes(
    r"""

/* Small-organisation Administration: common jobs first, infrastructure details later. */
(()=>{
 if(window.__fieldoraAdministrationManagementWired)return;
 window.__fieldoraAdministrationManagementWired=true;
 const byId=id=>document.getElementById(id);
 const html=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 let selectedUser="";

 function showManagementPanel(name){
  ["users","storage"].forEach(item=>{
   const panel=byId(`administration-${item}-panel`),button=byId(`administration-${item}-tab`);
   if(panel)panel.hidden=item!==name;
   if(button)button.setAttribute("aria-selected",String(item===name));
  });
  if(name==="users")loadAdministrationUsers();
  if(name==="storage")loadAdministrationStorage();
 }

 function renderUsers(items){
  const target=byId("administration-users-list");if(!target)return;
  target.innerHTML=items.length?items.map(user=>`<button class="row" type="button" data-administration-user="${html(user.identity_id)}"><strong>${html(user.display_name)}</strong><span>${html(user.username||"No local sign-in")}</span><span class="pill">${user.enabled?"Active":"Inactive"}</span><span>${html((user.roles||[]).join(", ")||"No direct role")}</span></button>`).join(""):'<div class="empty">No user accounts in this organisation.</div>';
  target.querySelectorAll("[data-administration-user]").forEach(button=>button.addEventListener("click",()=>selectAdministrationUser(button.dataset.administrationUser||"")));
 }

 async function loadAdministrationUsers(){
  const target=byId("administration-users-list");if(!target)return;
  try{const result=await api("/api/v1/administration/users",{purpose:"administration"});target.dataset.users=JSON.stringify(result.items||[]);renderUsers(result.items||[])}
  catch(error){target.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 }

 function selectAdministrationUser(identityId){
  const target=byId("administration-users-list"),items=JSON.parse(target?.dataset.users||"[]"),user=items.find(item=>item.identity_id===identityId);if(!user)return;
  selectedUser=identityId;
  byId("administration-user-editor").hidden=false;
  byId("administration-user-editor-title").textContent=user.display_name;
  byId("administration-user-editor-account").textContent=`${user.username||"No local sign-in"} · ${user.enabled?"Active":"Inactive"}`;
  byId("administration-user-roles").value=(user.roles||[]).join(", ");
  byId("administration-user-toggle").textContent=user.enabled?"Deactivate user":"Activate user";
  byId("administration-user-toggle").dataset.enabled=String(!user.enabled);
  byId("administration-user-password").value="";
  byId("administration-user-editor")?.scrollIntoView({block:"nearest"});
 }

 async function createAdministrationUser(){
  const status=byId("administration-user-create-status");
  const displayName=byId("administration-user-name").value.trim(),username=byId("administration-user-username").value.trim(),password=byId("administration-user-create-password").value,roles=byId("administration-user-create-roles").value.split(",").map(x=>x.trim()).filter(Boolean);
  if(!displayName||!username||password.length<12){status.textContent="Name, username and a password of at least 12 characters are required.";return}
  try{
   await api("/api/v1/administration/users",{method:"POST",purpose:"administration",body:JSON.stringify({display_name:displayName,username,password,roles})});
   status.textContent="User created.";
   byId("administration-user-name").value="";byId("administration-user-username").value="";byId("administration-user-create-password").value="";byId("administration-user-create-roles").value="";
   await loadAdministrationUsers();
  }catch(error){status.textContent=error.message}
 }

 async function toggleAdministrationUser(){
  if(!selectedUser)return;
  const enabled=byId("administration-user-toggle").dataset.enabled==="true",status=byId("administration-user-edit-status");
  try{await api(`/api/v1/administration/users/${encodeURIComponent(selectedUser)}/status`,{method:"POST",purpose:"administration",body:JSON.stringify({enabled})});status.textContent=enabled?"User activated.":"User deactivated and active sessions revoked.";await loadAdministrationUsers();selectAdministrationUser(selectedUser)}catch(error){status.textContent=error.message}
 }

 async function saveAdministrationRoles(){
  if(!selectedUser)return;
  const roles=byId("administration-user-roles").value.split(",").map(x=>x.trim()).filter(Boolean),status=byId("administration-user-edit-status");
  try{await api(`/api/v1/administration/users/${encodeURIComponent(selectedUser)}/roles`,{method:"PUT",purpose:"administration",body:JSON.stringify({roles})});status.textContent="Roles updated.";await loadAdministrationUsers();selectAdministrationUser(selectedUser)}catch(error){status.textContent=error.message}
 }

 async function resetAdministrationPassword(){
  if(!selectedUser)return;
  const password=byId("administration-user-password").value,status=byId("administration-user-edit-status");
  if(password.length<12){status.textContent="New password must contain at least 12 characters.";return}
  try{await api(`/api/v1/administration/users/${encodeURIComponent(selectedUser)}/password`,{method:"POST",purpose:"administration",body:JSON.stringify({password})});status.textContent="Password reset. Existing sessions for this user were revoked.";byId("administration-user-password").value=""}catch(error){status.textContent=error.message}
 }

 async function loadAdministrationStorage(){
  const target=byId("administration-storage-list");if(!target)return;
  try{
   const [sources,overview]=await Promise.all([api("/api/v1/linked-storage/sources",{purpose:"administration"}).catch(()=>({items:[]})),api("/api/v1/operator/overview",{purpose:"administration"})]);
   const archives=overview.linked_archives||sources.items||[];
   target.innerHTML=archives.length?archives.map(item=>`<div class="row"><strong>${html(item.display_name||item.name||item.storage_id||"Linked archive")}</strong><span class="pill">${item.enabled===false?"Disabled":item.stale?"Needs attention":"Ready"}</span><span>${item.read_only===false?"":"Read only"}</span></div>`).join(""):'<div class="empty">No storage or linked archive has been connected yet.</div>';
  }catch(error){target.innerHTML=`<div class="empty">${html(error.message)}</div>`}
 }

 function openStorageSetup(){
  showPage("operator");
  setTimeout(()=>{
   const section=byId("operator-linked-service-enroll")?.closest("section")||byId("operator-linked-archives")?.closest("section");
   section?.scrollIntoView({behavior:"smooth",block:"start"});byId("operator-linked-service-name")?.focus();
  },0);
 }

 function enhanceAdministration(){
  const page=byId("page-administration");if(!page)return false;
  if(byId("administration-organisation-management"))return true;
  const section=document.createElement("section");section.className="card section";section.id="administration-organisation-management";
  section.innerHTML=`<h2>Organisation management</h2><p class="muted">The everyday administrator tools for a small organisation.</p><div class="workspace-subnav" id="administration-simple-menu"><button id="administration-users-tab" type="button" aria-selected="true">Users & access</button><button id="administration-storage-tab" type="button" aria-selected="false">Storage & archives</button></div>
  <div id="administration-users-panel" class="section"><div class="top"><div><h3>Users & access</h3><p class="muted">Create accounts, activate or deactivate users, reset passwords and assign direct organisation roles.</p></div><button id="administration-users-refresh" type="button">Refresh</button></div><div id="administration-users-list" class="list"></div><h3>Add user</h3><div class="form-grid"><label>Name<input id="administration-user-name" autocomplete="name"></label><label>Username<input id="administration-user-username" autocomplete="username"></label><label>Temporary password<input id="administration-user-create-password" type="password" autocomplete="new-password"></label><label>Roles (comma separated)<input id="administration-user-create-roles" placeholder="researcher"></label></div><div class="actions section"><button id="administration-user-create" class="primary" type="button">Create user</button></div><p id="administration-user-create-status" class="status"></p><section id="administration-user-editor" class="section" hidden><h3 id="administration-user-editor-title">User</h3><p id="administration-user-editor-account" class="muted"></p><label>Roles (comma separated)<input id="administration-user-roles"></label><div class="actions section"><button id="administration-user-save-roles" type="button">Save roles</button><button id="administration-user-toggle" type="button">Deactivate user</button></div><label>New password<input id="administration-user-password" type="password" autocomplete="new-password"></label><div class="actions section"><button id="administration-user-reset-password" type="button">Reset password</button></div><p id="administration-user-edit-status" class="status"></p></section></div>
  <div id="administration-storage-panel" class="section" hidden><h3>Storage & archives</h3><p class="muted">See what is connected and start the guided setup without needing to know container paths or service identifiers.</p><div id="administration-storage-list" class="list"></div><div class="actions section"><button id="administration-storage-refresh" type="button">Refresh</button><button id="administration-storage-add" class="primary" type="button">Add storage or archive</button></div><details class="section"><summary>Advanced setup details</summary><p class="muted">Fieldora keeps filesystem roots, private keys, CA material and storage credentials on the trusted storage host. Advanced enrollment and mTLS details are available only when you continue to storage setup.</p></details></div>`;
  const firstCard=page.querySelector(".card");if(firstCard)firstCard.before(section);else page.appendChild(section);
  byId("administration-users-tab").onclick=()=>showManagementPanel("users");byId("administration-storage-tab").onclick=()=>showManagementPanel("storage");
  byId("administration-users-refresh").onclick=loadAdministrationUsers;byId("administration-user-create").onclick=createAdministrationUser;byId("administration-user-toggle").onclick=toggleAdministrationUser;byId("administration-user-save-roles").onclick=saveAdministrationRoles;byId("administration-user-reset-password").onclick=resetAdministrationPassword;
  byId("administration-storage-refresh").onclick=loadAdministrationStorage;byId("administration-storage-add").onclick=openStorageSetup;
  const nav=document.querySelector('.sidebar .nav[data-page="administration"]');if(nav)nav.addEventListener("click",()=>setTimeout(loadAdministrationUsers,0));
  return true;
 }
 if(!enhanceAdministration()){const observer=new MutationObserver(()=>{if(enhanceAdministration())observer.disconnect()});observer.observe(document.body,{childList:true,subtree:true})}
})();
""",
    "utf-8",
)


def patch_administration_management_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _ADMINISTRATION_MANAGEMENT_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _ADMINISTRATION_MANAGEMENT_WEB_PATCH,
        response.content_type,
        response.headers,
    )
