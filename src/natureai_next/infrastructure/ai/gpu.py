"""Centralized bounded GPU lease and adaptive batching policies."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GpuLease:
    owner: str
    exclusive: bool


class GpuResourceCoordinator:
    def __init__(self, *, max_shared_leases: int = 1) -> None:
        if max_shared_leases < 1:
            raise ValueError("max_shared_leases must be positive")
        self._condition = threading.Condition()
        self._exclusive_owner: str | None = None
        self._shared_owners: set[str] = set()
        self._max_shared = max_shared_leases

    @contextmanager
    def acquire(
        self, owner: str, *, exclusive: bool = True, timeout_seconds: float | None = None
    ) -> Iterator[GpuLease]:
        if not owner:
            raise ValueError("GPU lease owner is required")
        with self._condition:
            accepted = self._condition.wait_for(
                lambda: self._can_acquire(owner, exclusive), timeout=timeout_seconds
            )
            if not accepted:
                raise TimeoutError("GPU lease acquisition timed out")
            if exclusive:
                self._exclusive_owner = owner
            else:
                self._shared_owners.add(owner)
        try:
            yield GpuLease(owner, exclusive)
        finally:
            with self._condition:
                if exclusive:
                    if self._exclusive_owner == owner:
                        self._exclusive_owner = None
                else:
                    self._shared_owners.discard(owner)
                self._condition.notify_all()

    def _can_acquire(self, owner: str, exclusive: bool) -> bool:
        if exclusive:
            return self._exclusive_owner in (None, owner) and not (self._shared_owners - {owner})
        return self._exclusive_owner in (None, owner) and (
            owner in self._shared_owners or len(self._shared_owners) < self._max_shared
        )


def adaptive_batch_sizes(initial: int) -> tuple[int, ...]:
    if initial < 1:
        raise ValueError("initial batch size must be positive")
    sizes: list[int] = []
    current = initial
    while current >= 1:
        sizes.append(current)
        if current == 1:
            break
        current = max(1, current // 2)
    return tuple(sizes)


def estimate_initial_batch_size(
    *,
    available_memory_bytes: int | None,
    reservation_bytes: int,
    estimated_bytes_per_item: int,
    configured_maximum: int,
) -> int:
    """Choose a conservative batch size from currently available VRAM."""
    if reservation_bytes < 0 or estimated_bytes_per_item < 1 or configured_maximum < 1:
        raise ValueError("invalid GPU batch estimation inputs")
    if available_memory_bytes is None:
        return 1
    usable = max(0, available_memory_bytes - reservation_bytes)
    return max(1, min(configured_maximum, usable // estimated_bytes_per_item))
