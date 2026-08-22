from __future__ import annotations

import threading
from pathlib import Path

import natureai_next
from natureai_next.application.activity_contracts import (
    ActivityRegistry,
    ActivitySnapshot,
    ActivityState,
    OperationalHealth,
)
from natureai_next.application.operational_diagnostics import OperationalDiagnosticsService
from natureai_next.application.resources import ResourceBroker, ResourceUnavailable


class Source:
    def __init__(self):
        self.items = (ActivitySnapshot("1", "imports", "import", "Import", ActivityState.RUNNING, 1, 2, "file", modified_at_us=2),)
    def list_activity(self, limit=100): return self.items[:limit]
    def cancel_activity(self, activity_id): return activity_id == "1"
    def retry_activity(self, activity_id): return False


def test_build31_identity():
    assert natureai_next.__version__ == "5.4.0"
    assert Path("VERSION").read_text(encoding="utf-8").strip() == natureai_next.__version__


def test_registry_federates_activity_and_health():
    registry = ActivityRegistry(); registry.register("imports", Source())
    assert registry.source_names == ("imports",)
    assert registry.list_activity()[0].title == "Import"
    health = registry.list_health()[0]
    assert health.state is OperationalHealth.BUSY
    assert registry.cancel("imports", "1") is True
    assert registry.cancel("missing", "1") is False


def test_resource_broker_is_bounded_and_observable():
    broker = ResourceBroker({"cpu": 1})
    entered = threading.Event(); release = threading.Event()
    def worker():
        with broker.acquire("cpu"):
            entered.set(); release.wait(2)
    thread = threading.Thread(target=worker); thread.start(); assert entered.wait(1)
    try:
        with broker.acquire("cpu", timeout=0.01):
            raise AssertionError("lease should not be granted")
    except ResourceUnavailable:
        pass
    snapshot = {item.resource: item for item in broker.snapshot()}["cpu"]
    assert snapshot.in_use == 1
    release.set(); thread.join(2)
    assert broker.wait_until_idle()


def test_diagnostics_unifies_control_plane_without_owning_execution():
    registry = ActivityRegistry(); registry.register("imports", Source())
    diagnostics = OperationalDiagnosticsService(registry, ResourceBroker()).capture()
    assert diagnostics.activity_sources == ("imports",)
    assert diagnostics.active_activity_count == 1
    assert diagnostics.thread_count >= 1
    assert diagnostics.resources
