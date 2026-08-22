"""Runtime capability registry for modular Aperture features."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    key: str
    title: str
    dependencies: tuple[str, ...] = ()
    optional: bool = True


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    key: str
    state: CapabilityState
    message: str = ""


class CapabilityRegistry:
    """Registers feature capabilities without activating them during startup."""

    def __init__(self, descriptors: Iterable[CapabilityDescriptor] = ()) -> None:
        items = tuple(descriptors)
        keys = [item.key for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("capability keys must be unique")
        self._descriptors = {item.key: item for item in items}
        self._activators: dict[str, Callable[[], object]] = {}
        self._instances: dict[str, object] = {}
        self._errors: dict[str, str] = {}

    def register(self, descriptor: CapabilityDescriptor, activator: Callable[[], object]) -> None:
        if descriptor.key in self._descriptors:
            raise ValueError(f"duplicate capability: {descriptor.key}")
        self._descriptors[descriptor.key] = descriptor
        self._activators[descriptor.key] = activator

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptor(self, key: str) -> CapabilityDescriptor:
        try:
            return self._descriptors[key]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {key}") from exc

    def status(self, key: str) -> CapabilityStatus:
        self.descriptor(key)
        if key in self._instances:
            return CapabilityStatus(key, CapabilityState.ACTIVE)
        if key in self._errors:
            return CapabilityStatus(key, CapabilityState.UNAVAILABLE, self._errors[key])
        return CapabilityStatus(key, CapabilityState.AVAILABLE)

    def activate(self, key: str) -> object:
        if key in self._instances:
            return self._instances[key]
        descriptor = self.descriptor(key)
        for dependency in descriptor.dependencies:
            self.activate(dependency)
        activator = self._activators.get(key)
        if activator is None:
            raise RuntimeError(f"capability has no activator: {key}")
        try:
            instance = activator()
        except Exception as exc:
            self._errors[key] = str(exc)
            raise
        self._instances[key] = instance
        self._errors.pop(key, None)
        return instance

    def deactivate(self, key: str) -> None:
        self._instances.pop(key, None)


def build_foundation_capability_registry(subsystems) -> CapabilityRegistry:
    """Register optional foundation capabilities without activating their databases."""
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDescriptor("maps.offline", "Offline Maps"),
        lambda: subsystems.activate("maps.offline"),
    )
    registry.register(
        CapabilityDescriptor("taxonomy.reference", "Taxonomy Reference"),
        lambda: subsystems.activate("taxonomy.reference"),
    )
    return registry
