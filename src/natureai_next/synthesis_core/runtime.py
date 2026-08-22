"""Small in-process router that preserves the existing worker boundary.

Worker-backed engines may be registered behind this API without changing their
current process model.
"""

from __future__ import annotations

from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityEngine,
    CapabilityRequest,
    CapabilityResult,
)


class InProcessCapabilityRouter:
    def __init__(self) -> None:
        self._engines: dict[str, CapabilityEngine] = {}
        self._active: set[str] = set()

    def register(self, engine: CapabilityEngine, *, active: bool = True) -> None:
        capability_id = engine.descriptor.capability_id
        if capability_id in self._engines:
            raise ValueError(f"duplicate capability: {capability_id}")
        self._engines[capability_id] = engine
        if active:
            self._active.add(capability_id)

    def replace(self, engine: CapabilityEngine, *, active: bool = True) -> None:
        """Atomically replace a capability registration used by installed models."""
        capability_id = engine.descriptor.capability_id
        previous = self._engines.get(capability_id)
        if previous is not None and previous is not engine:
            previous.release()
        self._engines[capability_id] = engine
        if active:
            self._active.add(capability_id)
        else:
            self._active.discard(capability_id)

    def discover(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._engines[key].descriptor for key in sorted(self._engines))

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        if request.capability_id not in self._active:
            raise RuntimeError(f"capability is inactive: {request.capability_id}")
        try:
            engine = self._engines[request.capability_id]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {request.capability_id}") from exc
        return engine.execute(request)

    def execute_with_context(self, request: CapabilityRequest, *, cancellation, progress):
        if request.capability_id not in self._active:
            raise RuntimeError(f"capability is inactive: {request.capability_id}")
        try:
            engine = self._engines[request.capability_id]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {request.capability_id}") from exc
        execute = getattr(engine, "execute_with_context", None)
        if callable(execute):
            return execute(request, cancellation=cancellation, progress=progress)
        cancellation.raise_if_requested()
        return engine.execute(request)

    def activate(self, capability_id: str) -> None:
        if capability_id not in self._engines:
            raise KeyError(f"unknown capability: {capability_id}")
        self._active.add(capability_id)

    def deactivate(self, capability_id: str) -> None:
        engine = self._engines.get(capability_id)
        if engine is None:
            raise KeyError(f"unknown capability: {capability_id}")
        engine.release()
        self._active.discard(capability_id)

    def remove(self, capability_id: str) -> None:
        self.deactivate(capability_id)
        del self._engines[capability_id]
