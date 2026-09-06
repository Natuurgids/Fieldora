from __future__ import annotations

from natureai_next.server.capacity_module_web import _CAPACITY_MODULE_PATCH
from natureai_next.server.modular_shell_web import modular_shell_manifest
from natureai_next.server.web_module_contracts import foundation_registry


def test_capacity_requires_notification_contract_in_registry_and_manifest() -> None:
    registry = foundation_registry()
    spec = registry.module("capacity")
    manifest = {item["module_id"]: item for item in modular_shell_manifest()}

    assert spec.requires_contracts == (
        "notifications.publish",
        "projects.context.select",
        "projects.toolbar.extend",
    )
    assert manifest["capacity"]["requires_contracts"] == list(spec.requires_contracts)


def test_capacity_reports_shared_errors_through_notification_contract() -> None:
    script = _CAPACITY_MODULE_PATCH.decode("utf-8")

    assert 'resolve?.("notifications.publish")' in script
    assert (
        'notifications()?.publish?.(String(text),{level:"error",source_module:moduleId})'
        in script
    )
    assert 'node.textContent=text;node.classList.add("error")' in script
    assert 'new CustomEvent("fieldora:module-error"' not in script
