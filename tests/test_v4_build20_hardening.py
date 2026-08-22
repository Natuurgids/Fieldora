from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import pytest

from natureai_next.application.capability_execution import (
    CapabilityExecutionPool,
    CapabilityRunState,
)
from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceRemovalOptions,
    SourceState,
)
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


def _registry(tmp_path: Path) -> SourceRegistryService:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return SourceRegistryService(path)


def test_source_dependency_blocks_activation_and_removal(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    registry.register(SourceRecord("base", "source", "Base", "1", SourceState.INSTALLED))
    registry.attach_installation("base", runtime_path=runtime)
    registry.register(SourceRecord("child", "capability", "Child", "1", SourceState.INACTIVE))
    registry.attach_installation("child", runtime_path=runtime)
    registry.add_dependency("child", "base")
    registry.activate("child")
    assert registry.get("child").state is SourceState.INSTALLED
    with pytest.raises(RuntimeError, match="active dependents"):
        registry.remove("base", SourceRemovalOptions())
    registry.set_state("child", SourceState.INACTIVE)
    registry.remove("base", SourceRemovalOptions())
    assert registry.get("base").state is SourceState.REMOVED
    with pytest.raises(RuntimeError, match="dependencies are unavailable"):
        registry.activate("child")


def test_execution_pool_bounds_deduplicates_and_shuts_down() -> None:
    pool = CapabilityExecutionPool(max_workers=1, max_pending=2)
    gate = Event()

    def blocked(cancel, progress):
        progress(1, 2, "waiting")
        while not gate.wait(0.01):
            cancel.raise_if_requested()
        return "done"

    first = pool.submit(blocked, run_key="same")
    with pytest.raises(RuntimeError, match="already queued or running"):
        pool.submit(blocked, run_key="same")
    second = pool.submit(blocked, run_key="second")
    with pytest.raises(RuntimeError, match="queue is full"):
        pool.submit(blocked, run_key="third")
    assert pool.active_count == 2
    second.cancel()
    gate.set()
    assert first.result(timeout=2) == "done"
    deadline = time.monotonic() + 2
    while (
        second.progress.state not in {CapabilityRunState.CANCELLED, CapabilityRunState.CANCELLING}
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    pool.shutdown(wait=True, cancel_futures=True)
    with pytest.raises(RuntimeError, match="shut down"):
        pool.submit(blocked)
