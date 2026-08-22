from __future__ import annotations

from pathlib import Path


def test_gallery_workers_never_decode_originals() -> None:
    source = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    worker_start = source.index("class _ThumbnailWorker")
    worker_end = source.index("class _MetadataSaveWorker", worker_start)
    worker = source[worker_start:worker_end]

    assert "source_path=None" in worker
    assert "source_path=self._source" not in worker
    assert "durable background JobEngine" in worker


def test_thumbnail_checks_pause_when_workspace_is_inactive() -> None:
    source = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    assert "if not self._active or self._scrolling" in source
    assert "self._thumbnail_queue.clear()" in source
    assert "QTimer.singleShot(0, self._schedule_visible_thumbnails)" in source


def test_thumbnail_activity_is_visible_and_polled_without_blocking() -> None:
    source = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    assert 'QLabel("Thumbnails idle")' in source
    assert "awaiting background generation" in source
    assert "self._thumbnail_poll_timer.setInterval(10000)" in source
    assert "Thumbnail queued in background; you can continue working" in source


def test_startup_reconciliation_runs_on_delayed_daemon_timer() -> None:
    source = Path("src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")
    assert "thumbnail_reconcile = threading.Timer(" in source
    assert "thumbnail_reconcile.daemon = True" in source
    assert "thumbnail_reconcile.start()" in source
    assert "io_workers=1" in source
