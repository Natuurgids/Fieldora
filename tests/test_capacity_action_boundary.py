from __future__ import annotations

from natureai_next.server.capacity_module_web import _CAPACITY_MODULE_PATCH
from natureai_next.server.project_capacity_integration_web import (
    _PROJECT_CAPACITY_INTEGRATION_PATCH,
)
from natureai_next.server.web_module_contract_runtime import _RUNTIME_CONTRACT_PATCH
from natureai_next.server.web_module_contracts import foundation_registry


def test_capacity_open_action_has_declared_owner_and_runtime_registry() -> None:
    owner = foundation_registry().action_owner("capacity.project.open")
    assert owner is not None
    assert owner.module_id == "capacity"

    runtime = _RUNTIME_CONTRACT_PATCH.decode("utf-8")
    assert "actionOwners=new Map(),actions=new Map()" in runtime
    assert "(window.FieldoraModules?.specs||[])" in runtime
    assert "function actionOwner(action)" in runtime
    assert "function registerAction(action,moduleId,implementation)" in runtime
    assert "fieldora:action-registered" in runtime
    assert "function resolveAction(action)" in runtime
    assert "actionOwner,registerAction,resolveAction,requireAction" in runtime


def test_capacity_registers_its_open_project_action() -> None:
    capacity = _CAPACITY_MODULE_PATCH.decode("utf-8")

    assert 'const moduleId="capacity"' in capacity
    assert 'const openProjectAction=Object.freeze({openProject})' in capacity
    assert 'runtime.actionOwner?.("capacity.project.open")!==moduleId' in capacity
    assert 'runtime.resolveAction?.("capacity.project.open")' in capacity
    assert 'runtime.registerAction?.("capacity.project.open",moduleId,openProjectAction)' in capacity
    assert 'addEventListener("fieldora:contracts-ready",registerOpenProjectAction' in capacity


def test_project_capacity_integration_resolves_action_without_capacity_global() -> None:
    integration = _PROJECT_CAPACITY_INTEGRATION_PATCH.decode("utf-8")

    assert 'const ownerModule="capacity",entryKey="capacity.project.open"' in integration
    assert 'resolveAction?.(entryKey)' in integration
    assert "const action=capacityProject()" in integration
    assert "await action.openProject(pid)" in integration
    assert "window.FieldoraCapacity" not in integration
