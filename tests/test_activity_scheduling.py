from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from natureai_next.ui.qt import activity as activity_module


def _center(tmp_path, monkeypatch):
    monkeypatch.setattr(activity_module, "user_state_dir", lambda *_args, **_kwargs: str(tmp_path))
    center = activity_module.ActivityCenter()
    launched: list[str] = []

    def fake_launch(record, operation, *, notify=True):
        launched.append(record.activity_id)

    monkeypatch.setattr(center, "_launch", fake_launch)
    return center, launched


def test_offline_map_activities_use_bounded_worker_budget(tmp_path, monkeypatch):
    center, launched = _center(tmp_path, monkeypatch)
    center._kind_concurrency["offline-map.prepare"] = 3

    records = [
        center.start(
            title=f"Map {index}",
            detail="prepare",
            operation=lambda progress: None,
            kind="offline-map.prepare",
        )
        for index in range(5)
    ]

    assert len(launched) == 3
    assert sum(record.state == "running" for record in records) == 3
    assert sum(record.state == "queued" for record in records) == 2


def test_finishing_worker_promotes_oldest_queued_activity(tmp_path, monkeypatch):
    center, launched = _center(tmp_path, monkeypatch)
    center._kind_concurrency["offline-map.prepare"] = 1

    first = center.start("First", "prepare", lambda progress: None, kind="offline-map.prepare")
    second = center.start("Second", "prepare", lambda progress: None, kind="offline-map.prepare")

    assert first.state == "running"
    assert second.state == "queued"

    first.state = "completed"
    center._cleanup(first.activity_id)

    assert second.state == "running"
    assert launched[-1] == second.activity_id


def test_queued_activity_can_be_cancelled_without_worker(tmp_path, monkeypatch):
    center, _ = _center(tmp_path, monkeypatch)
    center._kind_concurrency["offline-map.prepare"] = 0
    record = center.start("Queued", "prepare", lambda progress: None, kind="offline-map.prepare")

    center.cancel(record)

    assert record.state == "cancelled"
    assert "before" in record.message.lower()
