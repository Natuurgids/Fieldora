"""Runtime registry for replaceable managed-web module contracts."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import WebModuleRegistry, foundation_registry


def runtime_contract_manifest(
    registry: WebModuleRegistry | None = None,
) -> tuple[dict[str, object], ...]:
    """Return browser-safe provider/consumer declarations in registry order."""

    if registry is None:
        registry = foundation_registry()
    return tuple(
        {
            "module_id": spec.module_id,
            "provides_contracts": list(spec.provides_contracts),
            "requires_contracts": list(spec.requires_contracts),
        }
        for spec in registry.as_mapping().values()
    )


def _runtime_script(registry: WebModuleRegistry | None = None) -> bytes:
    manifest = json.dumps(
        runtime_contract_manifest(registry), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "\n\n/* WEB-MODULE-CONTRACT-RUNTIME: replaceable module service boundary. */\n"
        "(()=>{\n"
        " if(window.__fieldoraModuleContractsWired)return;window.__fieldoraModuleContractsWired=true;\n"
        f" const declarations={manifest};\n"
        " const providers=new Map(),implementations=new Map();\n"
        " declarations.forEach(spec=>(spec.provides_contracts||[]).forEach(contract=>providers.set(contract,spec.module_id)));\n"
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
        " function requirements(moduleId){return [...(declaration(moduleId)?.requires_contracts||[])];}\n"
        " function unresolved(moduleId){return requirements(moduleId).filter(contract=>!implementations.has(contract));}\n"
        " const publicDeclarations=Object.freeze(declarations.map(spec=>Object.freeze({...spec,provides_contracts:Object.freeze([...spec.provides_contracts]),requires_contracts:Object.freeze([...spec.requires_contracts])})));\n"
        " window.FieldoraModuleContracts=Object.freeze({declarations:publicDeclarations,provider,register,resolve,require:requireContract,requirements,unresolved});\n"
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
