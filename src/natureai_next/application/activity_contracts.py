"""Federated operational contracts for independently executed Aperture subsystems.

The control plane is shared; execution queues, tables, databases and hardware remain
owned by each subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ActivityState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    RECOVERING = "recovering"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class OperationalHealth(StrEnum):
    HEALTHY = "healthy"
    BUSY = "busy"
    PAUSED = "paused"
    BLOCKED = "blocked"
    OFFLINE = "offline"
    RECOVERING = "recovering"
    FAILED = "failed"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    activity_id: str
    source: str
    kind: str
    title: str
    state: ActivityState
    current: int = 0
    total: int | None = None
    unit: str | None = None
    message: str | None = None
    error_code: str | None = None
    retryable: bool = False
    resource_class: str = "io"
    modified_at_us: int = 0
    cancellable: bool = True
    pausable: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshot:
    source: str
    state: OperationalHealth
    summary: str
    active_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    modified_at_us: int = 0


@runtime_checkable
class ActivitySource(Protocol):
    def list_activity(self, limit: int = 100) -> tuple[ActivitySnapshot, ...]: ...
    def cancel_activity(self, activity_id: str) -> bool: ...
    def retry_activity(self, activity_id: str) -> bool: ...


@runtime_checkable
class HealthSource(Protocol):
    def health_snapshot(self) -> SourceHealthSnapshot: ...


@runtime_checkable
class RecoveryProvider(Protocol):
    def recover_interrupted(self) -> int: ...
    def verify(self) -> tuple[str, ...]: ...
    def cleanup(self, *, preview: bool = True) -> tuple[str, ...]: ...


class ActivityRegistry:
    """Federates subsystem state without centralising execution or persistence."""

    def __init__(self) -> None:
        self._sources: dict[str, ActivitySource] = {}

    def register(self, name: str, source: ActivitySource) -> None:
        if not name or name in self._sources:
            raise ValueError(f"duplicate activity source: {name}")
        self._sources[name] = source

    def unregister(self, name: str) -> None:
        self._sources.pop(name, None)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._sources))

    def list_activity(self, limit: int = 200) -> tuple[ActivitySnapshot, ...]:
        if limit <= 0:
            return ()
        records: list[ActivitySnapshot] = []
        for source in self._sources.values():
            records.extend(source.list_activity(limit))
        records.sort(key=lambda item: item.modified_at_us, reverse=True)
        return tuple(records[:limit])

    def list_health(self) -> tuple[SourceHealthSnapshot, ...]:
        snapshots: list[SourceHealthSnapshot] = []
        for name, source in self._sources.items():
            if isinstance(source, HealthSource):
                snapshots.append(source.health_snapshot())
                continue
            activity = source.list_activity(500)
            active = sum(item.state in {ActivityState.QUEUED, ActivityState.RUNNING, ActivityState.RECOVERING} for item in activity)
            failed = sum(item.state is ActivityState.FAILED for item in activity)
            blocked = sum(item.state is ActivityState.BLOCKED for item in activity)
            state = OperationalHealth.FAILED if failed else OperationalHealth.BLOCKED if blocked else OperationalHealth.BUSY if active else OperationalHealth.HEALTHY
            snapshots.append(SourceHealthSnapshot(name, state, f"{active} active, {blocked} blocked, {failed} failed", active, failed, blocked))
        return tuple(sorted(snapshots, key=lambda item: item.source))

    def cancel(self, source: str, activity_id: str) -> bool:
        provider = self._sources.get(source)
        return False if provider is None else provider.cancel_activity(activity_id)

    def retry(self, source: str, activity_id: str) -> bool:
        provider = self._sources.get(source)
        return False if provider is None else provider.retry_activity(activity_id)
