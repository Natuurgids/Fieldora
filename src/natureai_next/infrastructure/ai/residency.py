"""Thread-safe model residency with idle eviction and deterministic ownership."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from natureai_next.ports.ai import AIExecutionProvider


@dataclass(slots=True)
class _Resident:
    model: object
    provider: AIExecutionProvider
    last_used: float
    borrowers: int = 0


class ModelLease:
    def __init__(self, manager: ModelResidencyManager, key: str, model: object) -> None:
        self._manager = manager
        self._key = key
        self.model = model

    def __enter__(self) -> object:
        return self.model

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._manager.release(self._key)


class ModelResidencyManager:
    def __init__(
        self, idle_seconds: float = 300.0, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        if idle_seconds < 0:
            raise ValueError("idle_seconds cannot be negative")
        self._idle_seconds = idle_seconds
        self._clock = monotonic
        self._lock = threading.RLock()
        self._items: dict[str, _Resident] = {}

    def acquire(
        self,
        key: str,
        provider: AIExecutionProvider,
        artifact: Path,
        *,
        device: str,
        precision: str,
    ) -> ModelLease:
        with self._lock:
            resident = self._items.get(key)
            if resident is None:
                resident = _Resident(
                    provider.load(artifact, device=device, precision=precision),
                    provider,
                    self._clock(),
                )
                self._items[key] = resident
            resident.borrowers += 1
            resident.last_used = self._clock()
            return ModelLease(self, key, resident.model)

    def release(self, key: str) -> None:
        with self._lock:
            resident = self._items.get(key)
            if resident is None or resident.borrowers < 1:
                raise RuntimeError("unbalanced model lease")
            resident.borrowers -= 1
            resident.last_used = self._clock()

    def evict_idle(self) -> tuple[str, ...]:
        evicted: list[str] = []
        with self._lock:
            now = self._clock()
            for key, resident in tuple(self._items.items()):
                if resident.borrowers == 0 and now - resident.last_used >= self._idle_seconds:
                    resident.provider.unload(resident.model)
                    del self._items[key]
                    evicted.append(key)
        return tuple(evicted)

    def close(self) -> None:
        with self._lock:
            if any(item.borrowers for item in self._items.values()):
                raise RuntimeError("cannot close while models are borrowed")
            for resident in self._items.values():
                resident.provider.unload(resident.model)
            self._items.clear()
