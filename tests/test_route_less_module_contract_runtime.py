from __future__ import annotations

import pytest

from natureai_next.server.modular_shell_composition import foundation_composition_registry
from natureai_next.server.web_module_contract_runtime import runtime_contract_manifest
from natureai_next.server.web_module_contracts import FOUNDATION_WEB_MODULES, WebModuleContractError
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
    WebModuleExtensionSpec,
)


def _route_ids() -> tuple[str, ...]:
    return tuple(spec.module_id for spec in FOUNDATION_WEB_MODULES)


def test_runtime_manifest_publishes_route_less_composition_identities() -> None:
    by_id = {item["module_id"]: item for item in runtime_contract_manifest()}

    operations = by_id[OPERATIONS_WEB_MODULE_ID]
    assert operations["host_route"] == "/operations"
    assert operations["provides_contracts"] == []
    assert operations["requires_contracts"] == []
    assert operations["optional_contracts"] == []

    facilities = by_id[FACILITIES_WEB_MODULE_ID]
    assert facilities["host_route"] == "/operations"
    assert facilities["provides_contracts"] == []
    assert facilities["requires_contracts"] == ["operations.workspace.host"]
    assert facilities["optional_contracts"] == []


def test_runtime_manifest_omits_uncomposed_route_less_modules() -> None:
    facilities_only = foundation_composition_registry(
        _route_ids() + (FACILITIES_WEB_MODULE_ID,)
    )
    facilities_by_id = {
        item["module_id"]: item for item in runtime_contract_manifest(facilities_only)
    }
    assert FACILITIES_WEB_MODULE_ID in facilities_by_id
    assert OPERATIONS_WEB_MODULE_ID not in facilities_by_id
    assert facilities_by_id[FACILITIES_WEB_MODULE_ID]["requires_contracts"] == [
        "operations.workspace.host"
    ]

    operations_only = foundation_composition_registry(
        _route_ids() + (OPERATIONS_WEB_MODULE_ID,)
    )
    operations_by_id = {
        item["module_id"]: item for item in runtime_contract_manifest(operations_only)
    }
    assert OPERATIONS_WEB_MODULE_ID in operations_by_id
    assert FACILITIES_WEB_MODULE_ID not in operations_by_id


def test_route_less_extension_contract_metadata_rejects_invalid_overlap() -> None:
    with pytest.raises(WebModuleContractError):
        WebModuleExtensionSpec(
            "example.extension",
            "Example",
            "/example",
            provides_contracts=("example.contract",),
            requires_contracts=("example.contract",),
        )
