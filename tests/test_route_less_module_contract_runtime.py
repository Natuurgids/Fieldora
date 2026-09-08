from __future__ import annotations

from natureai_next.server.modular_shell_composition import foundation_composition_registry
from natureai_next.server.web_module_contract_runtime import runtime_contract_manifest
from natureai_next.server.web_module_contracts import FOUNDATION_WEB_MODULES
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)


def _route_ids() -> tuple[str, ...]:
    return tuple(spec.module_id for spec in FOUNDATION_WEB_MODULES)


def test_runtime_manifest_publishes_route_less_composition_identities() -> None:
    by_id = {item["module_id"]: item for item in runtime_contract_manifest()}

    for module_id in (OPERATIONS_WEB_MODULE_ID, FACILITIES_WEB_MODULE_ID):
        declaration = by_id[module_id]
        assert declaration["host_route"] == "/operations"
        assert declaration["provides_contracts"] == []
        assert declaration["requires_contracts"] == []
        assert declaration["optional_contracts"] == []


def test_runtime_manifest_omits_uncomposed_route_less_modules() -> None:
    facilities_only = foundation_composition_registry(
        _route_ids() + (FACILITIES_WEB_MODULE_ID,)
    )
    facilities_by_id = {
        item["module_id"]: item for item in runtime_contract_manifest(facilities_only)
    }
    assert FACILITIES_WEB_MODULE_ID in facilities_by_id
    assert OPERATIONS_WEB_MODULE_ID not in facilities_by_id

    operations_only = foundation_composition_registry(
        _route_ids() + (OPERATIONS_WEB_MODULE_ID,)
    )
    operations_by_id = {
        item["module_id"]: item for item in runtime_contract_manifest(operations_only)
    }
    assert OPERATIONS_WEB_MODULE_ID in operations_by_id
    assert FACILITIES_WEB_MODULE_ID not in operations_by_id
