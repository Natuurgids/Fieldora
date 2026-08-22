"""Read-only operational diagnostics for field testing and Maintenance Centre."""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from natureai_next.application.activity_contracts import ActivityRegistry
from natureai_next.application.resources import ResourceBroker


@dataclass(frozen=True, slots=True)
class OperationalDiagnostics:
    generated_at_utc: str
    process_id: int
    thread_count: int
    threads: tuple[str, ...]
    activity_sources: tuple[str, ...]
    active_activity_count: int
    failed_activity_count: int
    resources: tuple[dict[str, object], ...]
    subsystem_health: tuple[dict[str, object], ...]


class OperationalDiagnosticsService:
    def __init__(self, registry: ActivityRegistry, broker: ResourceBroker) -> None:
        self._registry = registry
        self._broker = broker

    def capture(self) -> OperationalDiagnostics:
        activities = self._registry.list_activity(1000)
        threads = tuple(sorted(thread.name for thread in threading.enumerate()))
        return OperationalDiagnostics(
            generated_at_utc=datetime.now(UTC).isoformat(),
            process_id=os.getpid(),
            thread_count=len(threads),
            threads=threads,
            activity_sources=self._registry.source_names,
            active_activity_count=sum(item.state.value in {"queued", "running", "recovering", "stopping"} for item in activities),
            failed_activity_count=sum(item.state.value == "failed" for item in activities),
            resources=tuple(asdict(item) for item in self._broker.snapshot()),
            subsystem_health=tuple(asdict(item) for item in self._registry.list_health()),
        )
