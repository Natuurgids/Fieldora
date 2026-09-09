"""Runtime registry for replaceable managed-web module contracts."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.modular_shell_composition import foundation_composition_registry
from natureai_next.server.web_module_contracts import WebModuleRegistry


def runtime_contract_manifest(
    registry: WebModuleRegistry | None = None,
) -> tuple[dict[str, object], ...]:
    """Return browser-safe provider/consumer declarations in composition order."""

    if registry is None:
        registry = foundation_composition_registry()
    application_declarations = tuple(
        {
            "module_id": provider.provider_id,
            "provides_contracts": list(provider.provides_contracts),
            "requires_contracts": [],
            "optional_contracts": [],
        }
        for provider in registry.application_contract_providers().values()
    )
    module_declarations = tuple(
        {
            "module_id": spec.module_id,
            "provides_contracts": list(spec.provides_contracts),
            "requires_contracts": list(spec.requires_contracts),
            "optional_contracts": list(spec.optional_contracts),
        }
        for spec in registry.as_mapping().values()
    )
    extension_mapping = getattr(registry, "extension_mapping", None)
    extension_declarations = (
        tuple(
            {
                "module_id": spec.module_id,
                "host_route": spec.host_route,
                "provides_contracts": list(spec.provides_contracts),
                "requires_contracts": list(spec.requires_contracts),
                "optional_contracts": list(spec.optional_contracts),
            }
            for spec in extension_mapping().values()
        )
        if callable(extension_mapping)
        else ()
    )
    return application_declarations + module_declarations + extension_declarations


def _runtime_script(registry: WebModuleRegistry | None = None) -> bytes:
    manifest = json.dumps(
        runtime_contract_manifest(registry), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "\n\n/* WEB-MODULE-CONTRACT-RUNTIME: replaceable module service boundary. */\n"
        "(()=>{\n"
        " if(window.__fieldoraModuleContractsWired)return;window.__fieldoraModuleContractsWired=true;\n"
        f" const declarations={manifest};\n"
        " const providers=new Map(),implementations=new Map(),actionOwners=new Map(),actions=new Map();\n"
        " declarations.forEach(spec=>(spec.provides_contracts||[]).forEach(contract=>providers.set(contract,spec.module_id)));\n"
        " (window.FieldoraModules?.specs||[]).forEach(spec=>(spec.owns_actions||[]).forEach(action=>actionOwners.set(action,spec.module_id)));\n"
        " const token=value=>String(value||'').trim();\n"
        " const declaration=moduleId=>declarations.find(spec=>spec.module_id===token(moduleId))||null;\n"
        " function provider(contract){return providers.get(token(contract))||null;}\n"
        " function register(contract,moduleId,implementation){\n"
        "  const name=token(contract),owner=token(moduleId),expected=provider(name);\n"
        "  if(!expected)throw new Error(`Unknown module contract: ${name}`);\n"
        "  if(expected!==owner)throw new Error(`Contract ${name} is provided by ${expected}, not ${owner}`);\n"
        "  if(implementations.has(name))throw new Error(`Contract already registered: ${name}`);\n"
        "  if(implementation===null||implementation===undefined)throw new Error(`Contract implementation is required: ${name}`);\n"
        "  implementations.set(name,implementation);\n"
        "  document.dispatchEvent(new CustomEvent('fieldora:contract-registered',{detail:{contract:name,module_id:owner}}));\n"
        "  return implementation;\n"
        " }\n"
        " function resolve(contract){const name=token(contract);return implementations.has(name)?implementations.get(name):null;}\n"
        " function requireContract(contract){const name=token(contract),implementation=resolve(name);if(implementation===null)throw new Error(`Required module contract is not registered: ${name}`);return implementation;}\n"
        " function actionOwner(action){return actionOwners.get(token(action))||null;}\n"
        " function registerAction(action,moduleId,implementation){\n"
        "  const name=token(action),owner=token(moduleId),expected=actionOwner(name);\n"
        "  if(!expected)throw new Error(`Unknown module action: ${name}`);\n"
        "  if(expected!==owner)throw new Error(`Action ${name} is owned by ${expected}, not ${owner}`);\n"
        "  if(actions.has(name))throw new Error(`Action already registered: ${name}`);\n"
        "  if(implementation===null||implementation===undefined)throw new Error(`Action implementation is required: ${name}`);\n"
        "  actions.set(name,implementation);\n"
        "  document.dispatchEvent(new CustomEvent('fieldora:action-registered',{detail:{action:name,module_id:owner}}));\n"
        "  return implementation;\n"
        " }\n"
        " function resolveAction(action){const name=token(action);return actions.has(name)?actions.get(name):null;}\n"
        " function requireAction(action){const name=token(action),implementation=resolveAction(name);if(implementation===null)throw new Error(`Required module action is not registered: ${name}`);return implementation;}\n"
        " function requirements(moduleId){return [...(declaration(moduleId)?.requires_contracts||[])];}\n"
        " function unresolved(moduleId){return requirements(moduleId).filter(contract=>!implementations.has(contract));}\n"
        " const publicDeclarations=Object.freeze(declarations.map(spec=>Object.freeze({...spec,provides_contracts:Object.freeze([...spec.provides_contracts]),requires_contracts:Object.freeze([...spec.requires_contracts]),optional_contracts:Object.freeze([...(spec.optional_contracts||[])])})));\n"
        " window.FieldoraModuleContracts=Object.freeze({declarations:publicDeclarations,provider,register,resolve,require:requireContract,requirements,unresolved,actionOwner,registerAction,resolveAction,requireAction});\n"
        " if(provider('auth.current-user')==='application.auth'){\n"
        "  register('auth.current-user','application.auth',Object.freeze({current:()=>typeof me==='undefined'||!me?null:Object.freeze({...me})}));\n"
        " }\n"
        " if(provider('navigation.navigate')==='application.navigation'&&window.FieldoraModules?.navigate){\n"
        "  const navigate=(route,source='contract',historyMode='push')=>window.FieldoraModules.navigate(route,source,historyMode);\n"
        "  register('navigation.navigate','application.navigation',Object.freeze({navigate}));\n"
        " }\n"
        " if(provider('notifications.publish')==='application.notifications'){\n"
        "  const notificationHost=()=>{let node=document.getElementById('fieldora-app-notification');if(node)return node;node=document.createElement('div');node.id='fieldora-app-notification';node.hidden=true;node.setAttribute('role','status');node.setAttribute('aria-live','polite');(document.body||document.documentElement).appendChild(node);return node;};\n"
        "  const publishNotification=(message,options={})=>{const text=String(message||'').trim();if(!text)return null;const level=String(options.level||'info'),source_module=String(options.source_module||'');const detail=Object.freeze({message:text,level,source_module});const node=notificationHost();node.hidden=false;node.textContent=text;node.setAttribute('aria-live',level==='error'?'assertive':'polite');node.dataset.level=level;node.dataset.sourceModule=source_module;document.dispatchEvent(new CustomEvent('fieldora:notification',{detail}));if(level==='error')document.dispatchEvent(new CustomEvent('fieldora:module-error',{detail:{module_id:source_module,error:text}}));return detail;};\n"
        "  register('notifications.publish','application.notifications',Object.freeze({publish:publishNotification}));\n"
        " }\n"
        " if(provider('operations.workspace.host')==='application.operations-workspace'&&typeof loadOperations==='function'){\n"
        "  const operationsWorkspaceListeners=new Set();\n"
        "  const currentDomain=()=>typeof operationsDomain==='undefined'?null:String(operationsDomain);\n"
        "  const captureRecords=()=>{const node=document.getElementById('operations-list');let parsed=[];try{parsed=JSON.parse(node?.dataset.records||'[]')}catch(_error){}return Object.freeze((Array.isArray(parsed)?parsed:[]).map(record=>record&&typeof record==='object'?Object.freeze({...record}):record));};\n"
        "  let operationsWorkspaceRecords=captureRecords();\n"
        "  const currentRecords=()=>operationsWorkspaceRecords;\n"
        "  const baseOperationsLoad=loadOperations;\n"
        "  loadOperations=async function(){const result=await baseOperationsLoad();operationsWorkspaceRecords=captureRecords();const snapshot=Object.freeze({domain:currentDomain(),records:operationsWorkspaceRecords});operationsWorkspaceListeners.forEach(listener=>{try{listener(snapshot)}catch(error){console.error('Operations workspace subscriber failed',error)}});return result;};\n"
        "  const selectDomain=async domain=>{const next=token(domain);if(!next)throw new Error('Operations workspace domain is required');operationsDomain=next;return loadOperations();};\n"
        "  const subscribe=listener=>{if(typeof listener!=='function')throw new Error('Operations workspace subscriber must be a function');operationsWorkspaceListeners.add(listener);return ()=>operationsWorkspaceListeners.delete(listener);};\n"
        "  register('operations.workspace.host','application.operations-workspace',Object.freeze({currentDomain,records:currentRecords,selectDomain,refresh:()=>loadOperations(),subscribe}));\n"
        " }\n"
        " document.dispatchEvent(new CustomEvent('fieldora:contracts-ready',{detail:{contracts:Object.freeze([...providers.keys()])}}));\n"
        "})();\n"
    ).encode()


_RUNTIME_CONTRACT_PATCH = _runtime_script()


def patch_runtime_contracts_response(
    target: str,
    response: ApiResponse,
    *,
    registry: WebModuleRegistry | None = None,
) -> ApiResponse:
    """Append the runtime registry after the finalized modular shell exactly once."""

    patch = _RUNTIME_CONTRACT_PATCH if registry is None else _runtime_script(registry)
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or b"WEB-MODULAR-SHELL: registry-owned navigation bridge" not in response.body
        or patch in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + patch,
        response.content_type,
        response.headers,
    )
