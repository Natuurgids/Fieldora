from __future__ import annotations

import pytest

from natureai_next.server.facility_actions_web import _FACILITY_ACTIONS_PATCH
from natureai_next.server.facility_module_composition import _FACILITY_BASE_OMISSION_PATCH
from natureai_next.server.facility_web_compatibility import _FACILITY_WEB_PATCH
from natureai_next.server.modular_shell_composition import foundation_composition_registry
from natureai_next.server.offline_maps_web import _OFFLINE_MAPS_WEB_PATCH
from natureai_next.server.operations_module_composition import (
    _OPERATIONS_WITH_FACILITIES_PATCH,
    _OPERATIONS_WITHOUT_FACILITIES_PATCH,
)
from natureai_next.server.project_facility_workspace_web import (
    _PROJECT_FACILITY_WORKSPACE_PATCH,
)
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
    assert operations["requires_contracts"] == ["operations.workspace.host"]
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
    assert operations_by_id[OPERATIONS_WEB_MODULE_ID]["requires_contracts"] == [
        "operations.workspace.host"
    ]


def test_route_less_extension_contract_metadata_rejects_invalid_overlap() -> None:
    with pytest.raises(WebModuleContractError):
        WebModuleExtensionSpec(
            "example.extension",
            "Example",
            "/example",
            provides_contracts=("example.contract",),
            requires_contracts=("example.contract",),
        )


def test_facilities_browser_projections_use_workspace_contract() -> None:
    cockpit = _PROJECT_FACILITY_WORKSPACE_PATCH.decode("utf-8")
    omission = _FACILITY_BASE_OMISSION_PATCH.decode("utf-8")

    assert "operations.workspace.host" in cockpit
    assert "fieldora:contracts-ready" in cockpit
    assert "host.selectDomain" in cockpit
    assert "host.subscribe" in cockpit
    assert "operationsDomain" not in cockpit
    assert "loadOperations" not in cockpit

    assert "operations.workspace.host" in omission
    assert "fieldora:contracts-ready" in omission
    assert "host.currentDomain" in omission
    assert "host.selectDomain" in omission
    assert "operationsDomain" not in omission


def test_facilities_auxiliary_projections_subscribe_to_workspace_contract() -> None:
    actions = _FACILITY_ACTIONS_PATCH.decode("utf-8")
    planning = _FACILITY_WEB_PATCH.decode("utf-8")
    offline_maps = _OFFLINE_MAPS_WEB_PATCH.decode("utf-8")

    for script in (actions, planning, offline_maps):
        assert "operations.workspace.host" in script
        assert "fieldora:contracts-ready" in script
        assert "host.subscribe" in script
        assert 'nav[data-page="operations"]' not in script
        assert "operations-refresh" not in script


def test_operations_browser_omission_uses_public_contracts() -> None:
    facilities_host = _OPERATIONS_WITH_FACILITIES_PATCH.decode("utf-8")
    empty_host = _OPERATIONS_WITHOUT_FACILITIES_PATCH.decode("utf-8")

    assert "operations.workspace.host" in facilities_host
    assert "fieldora:contracts-ready" in facilities_host
    assert "host.currentDomain" in facilities_host
    assert "host.selectDomain" in facilities_host
    assert "operationsDomain" not in facilities_host
    assert "loadOperations" not in facilities_host

    assert 'resolve("navigation.navigate")' in empty_host
    assert 'navigation.navigate("/administration","operations","replace")' in empty_host
    assert "fieldora:contracts-ready" in empty_host
    assert "showPage" not in empty_host
