"""Lifecycle coordinator for independently mounted Fieldora web modules.

This is intentionally independent of a concrete browser framework.  Browser
adapters can implement ``WebModuleAdapter`` while the platform owns ordering,
state transitions and failure isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from natureai_next.server.web_module_contracts import WebModuleRegistry, WebModuleSpec


class WebModuleRuntimeError(RuntimeError):
    """Raised for invalid module lifecycle operations."""


class WebModuleState(StrEnum):
    UNMOUNTED = "unmounted"
    MOUNTING = "mounting"
    MOUNTED = "mounted"
    UNMOUNTING = "unmounting"
    FAILED = "failed"


class WebModuleAdapter(Protocol):
    """Browser/framework adapter controlled by the platform runtime."""

    def mount(self, spec: WebModuleSpec) -> None: ...

    def unmount(self, spec: WebModuleSpec) -> None: ...


@dataclass(frozen=True, slots=True)
class WebModuleRuntimeSnapshot:
    module_id: str
    state: WebModuleState
    error: str | None = None


class WebModuleRuntime:
    """Coordinates one active module at a time through explicit adapters."""

    def __init__(self, registry: WebModuleRegistry) -> None:
        self._registry = registry
        self._adapters: dict[str, WebModuleAdapter] = {}
        self._state: dict[str, WebModuleRuntimeSnapshot] = {
            module_id: WebModuleRuntimeSnapshot(module_id, WebModuleState.UNMOUNTED)
            for module_id in registry.as_mapping()
        }
        self._active_module_id: str | None = None

    def bind(self, module_id: str, adapter: WebModuleAdapter) -> None:
        self._registry.module(module_id)
        if module_id in self._adapters:
            raise WebModuleRuntimeError(f"module {module_id!r} already has an adapter")
        self._adapters[module_id] = adapter

    @property
    def active_module_id(self) -> str | None:
        return self._active_module_id

    def snapshot(self, module_id: str) -> WebModuleRuntimeSnapshot:
        self._registry.module(module_id)
        return self._state[module_id]

    def activate_route(self, route: str) -> WebModuleSpec:
        target = self._registry.resolve(route)
        if target is None:
            raise WebModuleRuntimeError(f"no module owns route {route!r}")
        self.activate(target.module_id)
        return target

    def activate(self, module_id: str) -> None:
        target = self._registry.module(module_id)
        if self._active_module_id == module_id:
            return

        for dependency in target.dependencies:
            if dependency not in self._adapters:
                raise WebModuleRuntimeError(
                    f"module {module_id!r} cannot activate: dependency {dependency!r} has no adapter"
                )

        if module_id not in self._adapters:
            raise WebModuleRuntimeError(f"module {module_id!r} has no adapter")

        previous = self._active_module_id
        if previous is not None:
            self._unmount(previous)

        self._mount(module_id)

    def deactivate(self) -> None:
        if self._active_module_id is not None:
            self._unmount(self._active_module_id)

    def _mount(self, module_id: str) -> None:
        spec = self._registry.module(module_id)
        adapter = self._adapters[module_id]
        self._state[module_id] = WebModuleRuntimeSnapshot(module_id, WebModuleState.MOUNTING)
        try:
            adapter.mount(spec)
        except Exception as exc:
            self._state[module_id] = WebModuleRuntimeSnapshot(
                module_id, WebModuleState.FAILED, str(exc)
            )
            self._active_module_id = None
            raise WebModuleRuntimeError(f"module {module_id!r} mount failed") from exc
        self._state[module_id] = WebModuleRuntimeSnapshot(module_id, WebModuleState.MOUNTED)
        self._active_module_id = module_id

    def _unmount(self, module_id: str) -> None:
        spec = self._registry.module(module_id)
        adapter = self._adapters.get(module_id)
        if adapter is None:
            raise WebModuleRuntimeError(f"module {module_id!r} has no adapter")

        self._state[module_id] = WebModuleRuntimeSnapshot(module_id, WebModuleState.UNMOUNTING)
        try:
            adapter.unmount(spec)
        except Exception as exc:
            self._state[module_id] = WebModuleRuntimeSnapshot(
                module_id, WebModuleState.FAILED, str(exc)
            )
            self._active_module_id = None
            raise WebModuleRuntimeError(f"module {module_id!r} unmount failed") from exc
        self._state[module_id] = WebModuleRuntimeSnapshot(module_id, WebModuleState.UNMOUNTED)
        self._active_module_id = None
