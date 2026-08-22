"""Shared capacity coordination for independent subsystem executors."""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


class ResourceUnavailable(RuntimeError):
    """Raised when a resource lease cannot be obtained within the requested time."""


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    resource: str
    capacity: int
    in_use: int
    available: int
    waiting: int


class _Pool:
    def __init__(self, capacity: int) -> None:
        self.capacity = max(1, int(capacity))
        self.semaphore = threading.BoundedSemaphore(self.capacity)
        self.in_use = 0
        self.waiting = 0
        self.lock = threading.Lock()


class ResourceBroker:
    """Coordinates capacity only; it never owns or executes subsystem work."""

    DEFAULT_LIMITS = {
        "io": 4,
        "high_io": 1,
        "cpu": 2,
        "gpu": 1,
        "database_writer": 1,
        "network": 2,
        "memory_heavy": 1,
    }

    def __init__(self, limits: dict[str, int] | None = None) -> None:
        merged = dict(self.DEFAULT_LIMITS)
        if limits:
            merged.update(limits)
        self._pools = {name: _Pool(count) for name, count in merged.items()}

    def ensure_resource(self, resource: str, capacity: int = 1) -> None:
        if resource not in self._pools:
            self._pools[resource] = _Pool(capacity)

    @contextmanager
    def acquire(self, resource: str, *, timeout: float | None = None) -> Iterator[None]:
        pool = self._pools.get(resource)
        if pool is None:
            raise KeyError(f"unknown resource class: {resource}")
        with pool.lock:
            pool.waiting += 1
        try:
            acquired = pool.semaphore.acquire(timeout=timeout) if timeout is not None else pool.semaphore.acquire()
        finally:
            with pool.lock:
                pool.waiting -= 1
        if not acquired:
            raise ResourceUnavailable(f"resource {resource!r} was unavailable")
        with pool.lock:
            pool.in_use += 1
        try:
            yield
        finally:
            with pool.lock:
                pool.in_use -= 1
            pool.semaphore.release()

    def snapshot(self) -> tuple[ResourceSnapshot, ...]:
        result = []
        for name, pool in sorted(self._pools.items()):
            with pool.lock:
                result.append(ResourceSnapshot(name, pool.capacity, pool.in_use, pool.capacity - pool.in_use, pool.waiting))
        return tuple(result)

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(item.in_use == 0 for item in self.snapshot()):
                return True
            time.sleep(0.01)
        return all(item.in_use == 0 for item in self.snapshot())
