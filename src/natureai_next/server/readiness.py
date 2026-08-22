"""Bounded, non-disclosing production dependency readiness."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    ready: bool
    checks: tuple[tuple[str, bool], ...]
    checked_at_epoch: int

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "checks": {name: passed for name, passed in self.checks},
            "checked_at_epoch": self.checked_at_epoch,
        }


class ReadinessMonitor:
    def __init__(
        self,
        checks: dict[str, Callable[[], bool]],
        *,
        cache_seconds: float = 2.0,
    ) -> None:
        if not checks:
            raise ValueError("at least one readiness check is required")
        if not 0 <= cache_seconds <= 60:
            raise ValueError("readiness cache must be between 0 and 60 seconds")
        self._checks = tuple(sorted(checks.items()))
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cached: tuple[float, ReadinessSnapshot] | None = None
        self._draining = False

    def begin_draining(self) -> None:
        with self._lock:
            self._draining = True
            self._cached = None

    def snapshot(self) -> ReadinessSnapshot:
        now = time.monotonic()
        with self._lock:
            if self._draining:
                return ReadinessSnapshot(
                    False, (("draining", False),), int(time.time())
                )
            if self._cached is not None and now - self._cached[0] < self._cache_seconds:
                return self._cached[1]
            results = []
            for name, check in self._checks:
                try:
                    passed = check() is True
                except Exception:
                    passed = False
                results.append((name, passed))
            snapshot = ReadinessSnapshot(
                all(passed for _, passed in results),
                tuple(results),
                int(time.time()),
            )
            self._cached = (now, snapshot)
            return snapshot
