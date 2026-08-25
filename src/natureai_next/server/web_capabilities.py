"""Zero-trust capability projection for the managed Fieldora web client.

The browser receives booleans only.  PBAC remains authoritative for every API call;
this projection exists solely to avoid disclosing navigation, actions, counts or
workspace names that the authenticated identity has no authority to use.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest, Identity, PolicyEffect
from natureai_next.server.api import ApiResponse

Rule = tuple[str, str, str]

_PAGE_RULES: dict[str, tuple[Rule, ...]] = {
    "library": (
        ("view", "asset", "research"),
        ("view", "collection", "research"),
    ),
    "observations": (("view", "observation", "research"),),
    "projects": (("view", "project", "research"),),
    "research-records": (
        ("view", "specimen", "research"),
        ("view", "encounter", "research"),
        ("view", "protocol", "research"),
        ("view", "survey_event", "research"),
        ("view", "enrichment", "research"),
        ("view", "sample", "research"),
        ("view", "laboratory_record", "research"),
    ),
    "dossiers": (("view", "dossier", "research"),),
    "capacity": (
        ("view", "allocation", "research"),
        ("view", "work_schedule", "research"),
        ("view", "obligation", "research"),
    ),
    "knowledge": (("view", "knowledge", "research"),),
    "governance": (("administer_contracts", "contract", "administration"),),
    "operations": (
        ("view", "operations_asset", "administration"),
        ("view", "operations_location", "administration"),
        ("view", "operations_drawing", "administration"),
    ),
    "intake-review": (
        ("view", "dossier_review", "research"),
        ("view_job", "job", "administration"),
    ),
    "aiadmin": (
        ("view", "ai_model", "administration"),
        ("view", "ai_provider", "administration"),
        ("view", "mcp_server", "administration"),
    ),
    "reference": (("view", "reference_value", "administration"),),
    "connectors": (("view", "connector", "administration"),),
    "operator": (
        ("view_job", "job", "administration"),
        ("storage.enable", "linked_storage", "administration"),
        ("storage.disable", "linked_storage", "administration"),
    ),
    "platform": (("administer_search", "search_index", "administration"),),
}

_ACTION_RULES: dict[str, tuple[Rule, ...]] = {
    "projects.create": (("create", "project", "research"),),
    "library.import": (("upload", "asset", "research"),),
    "aiadmin.manage": (("edit", "ai_model", "administration"),),
    "operator.manage": (
        ("storage.enable", "linked_storage", "administration"),
        ("storage.disable", "linked_storage", "administration"),
    ),
}


def _candidate_policies(application: Any, identity: Identity, rule: Rule):
    repository = getattr(application, "_access_repository", None)
    if repository is None:
        return ()
    action, resource_type, purpose = rule
    now = datetime.now(UTC).isoformat()
    candidates = []
    for policy in repository.policies():
        if not policy.enabled or policy.effect is not PolicyEffect.ALLOW:
            continue
        if action not in policy.actions and "*" not in policy.actions:
            continue
        if resource_type not in policy.resource_types and "*" not in policy.resource_types:
            continue
        if policy.organization_id and policy.organization_id != identity.organization_id:
            continue
        if policy.purposes and purpose not in policy.purposes:
            continue
        if policy.valid_from_utc and now < policy.valid_from_utc:
            continue
        if policy.valid_until_utc and now >= policy.valid_until_utc:
            continue
        if policy.subject_id:
            if policy.subject_id != identity.identity_id:
                continue
        elif policy.role_id:
            role_ids = set(
                repository.role_ids(
                    identity.identity_id,
                    identity.organization_id,
                    policy.project_id,
                )
            )
            if policy.role_id not in role_ids:
                continue
        else:
            continue
        candidates.append(policy)
    return tuple(candidates)


def _has_authority(application: Any, identity: Identity, rule: Rule) -> bool:
    """Return whether at least one real PBAC scope for this rule is allowed.

    Candidate scopes come only from policies already applicable to the identity.
    The final answer is still produced by PolicyDecisionService so explicit denies,
    active-contract checks and normal PBAC precedence remain authoritative.
    """

    action, resource_type, purpose = rule
    decisions = getattr(application, "_decisions", None)
    if decisions is None:
        return False
    for policy in _candidate_policies(application, identity, rule):
        request = AccessRequest(
            subject_id=identity.identity_id,
            action=action,
            resource_type=resource_type,
            resource_id=policy.resource_id,
            organization_id=identity.organization_id,
            project_id=policy.project_id,
            purpose=purpose,
            attributes=dict(policy.conditions),
        )
        if decisions.decide(request).allowed:
            return True
    return False


def _any_rule(application: Any, identity: Identity, rules: tuple[Rule, ...]) -> bool:
    return any(_has_authority(application, identity, rule) for rule in rules)


def capability_payload(application: Any, identity: Identity) -> dict[str, object]:
    pages = {
        name: _any_rule(application, identity, rules)
        for name, rules in _PAGE_RULES.items()
    }
    pages["research"] = any(
        pages[name] for name in ("projects", "research-records", "dossiers", "capacity")
    )
    pages["administration"] = any(
        pages[name]
        for name in (
            "governance",
            "operations",
            "intake-review",
            "aiadmin",
            "reference",
            "connectors",
            "operator",
            "platform",
        )
    )
    # Home and Help do not disclose governed object existence.  They remain the
    # safe authenticated landing/help surfaces when every governed workspace is denied.
    pages["home"] = True
    pages["help"] = True
    actions = {
        name: _any_rule(application, identity, rules)
        for name, rules in _ACTION_RULES.items()
    }
    return {"pages": pages, "actions": actions, "default_deny": True}


def web_capabilities_response(application: Any, headers: dict[str, str]) -> ApiResponse:
    try:
        _token, identity = application._identity(headers)
    except AuthenticationFailed:
        # Do not disclose whether any capability exists to an unauthenticated caller.
        return ApiResponse.json(401, {"error": "unauthorized"})
    return ApiResponse.json(200, capability_payload(application, identity))


_ZERO_TRUST_WEB_PATCH = bytes(
    r"""

/* Fieldora zero-trust UI projection: absent PBAC authority means absent UI. */
(()=>{
 if(window.__fieldoraZeroTrustUiWired)return;window.__fieldoraZeroTrustUiWired=true;
 const pageCapability={
  home:"home",library:"library",observations:"observations",projects:"projects",
  research:"research",dossiers:"dossiers",capacity:"capacity",knowledge:"knowledge",
  administration:"administration",operations:"operations","intake-review":"intake-review",
  aiadmin:"aiadmin",reference:"reference",connectors:"connectors",operator:"operator",
  platform:"platform",help:"help"
 };
 let capabilities={pages:{},actions:{}};
 let ready=false;
 const style=document.createElement("style");
 style.textContent='[data-fieldora-authorization-hidden="true"]{display:none!important}';
 document.head.appendChild(style);
 const allowed=page=>ready&&capabilities.pages?.[pageCapability[page]||page]===true;
 const mark=(node,hidden)=>{if(node)node.dataset.fieldoraAuthorizationHidden=hidden?"true":"false"};
 function apply(){
  document.querySelectorAll('[id^="page-"]').forEach(node=>{
   const page=node.id.slice(5);mark(node,!allowed(page));
  });
  document.querySelectorAll('[data-page]').forEach(node=>mark(node,!allowed(node.dataset.page)));
  document.querySelectorAll('[data-workspace-target]').forEach(node=>mark(node,!allowed(node.dataset.workspaceTarget)));
  document.querySelectorAll('[data-home-target]').forEach(node=>mark(node,!allowed(node.dataset.homeTarget)));
  document.querySelectorAll('.go-import').forEach(node=>mark(node,capabilities.actions?.['library.import']!==true));
  mark(document.querySelector('[data-library-view="import"]'),capabilities.actions?.['library.import']!==true);
  for(const id of ['new-project','portfolio-new-project'])mark(document.getElementById(id),capabilities.actions?.['projects.create']!==true);
  document.querySelectorAll('[data-register-offline-model]').forEach(node=>mark(node,capabilities.actions?.['aiadmin.manage']!==true));
  document.querySelectorAll('[data-linked-archive-action]').forEach(node=>mark(node,capabilities.actions?.['operator.manage']!==true));
 }
 function firstAllowed(){return ['home','library','observations','research','knowledge','administration','help'].find(allowed)||'home'}
 const baseShowPage=showPage;
 showPage=function(page){
  if(!ready)return;
  const target=allowed(page)?page:firstAllowed();
  baseShowPage(target);if(target!==page&&location.hash===`#${page}`)history.replaceState(null,'',`#${target}`);
 };
 async function refresh(){
  try{
   const payload=await baseApi('/api/v1/web/capabilities',{purpose:'ui'});
   if(!payload||payload.default_deny!==true||typeof payload.pages!=="object")throw new Error('invalid capability projection');
   capabilities=payload;ready=true;document.body.dataset.fieldoraCapabilities='ready';apply();
   const requested=(location.hash||'#home').slice(1);showPage(requested);
  }catch(_error){
   capabilities={pages:{},actions:{}};ready=false;delete document.body.dataset.fieldoraCapabilities;apply();
  }
 }
 const baseApi=api;
 api=async function(path,options={}){
  const result=await baseApi(path,options);
  const route=String(path||'').split('?',1)[0];
  if(route==='/api/v1/me'||(route==='/api/v1/session'&&String(options.method||'GET').toUpperCase()==='POST'))queueMicrotask(refresh);
  if(route==='/api/v1/session'&&String(options.method||'GET').toUpperCase()==='DELETE'){
   capabilities={pages:{},actions:{}};ready=false;delete document.body.dataset.fieldoraCapabilities;apply();
  }
  return result;
 };
 apply();
 const observer=new MutationObserver(()=>{if(ready)apply()});observer.observe(document.body,{childList:true,subtree:true});
 queueMicrotask(refresh);
})();
""",
    "utf-8",
)


def patch_zero_trust_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _ZERO_TRUST_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _ZERO_TRUST_WEB_PATCH,
        response.content_type,
        response.headers,
    )
