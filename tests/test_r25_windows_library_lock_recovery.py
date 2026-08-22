from __future__ import annotations

import json
from pathlib import Path

from natureai_next.infrastructure.filesystem import library_lock


def _write_lock(path: Path, *, pid: int = 17480, created_at_us: int = 1_000_000) -> None:
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "host": "Diablo001",
                "created_at_us": created_at_us,
                "process_start_id": None,
            }
        ),
        encoding="utf-8",
    )


def test_old_windows_lock_is_removed_when_pid_was_reused(tmp_path, monkeypatch):
    path = tmp_path / ".natureai-next.lock"
    _write_lock(path)
    monkeypatch.setattr(library_lock.os, "name", "nt")
    monkeypatch.setattr(library_lock.socket, "gethostname", lambda: "Diablo001")
    monkeypatch.setattr(library_lock, "_process_is_alive", lambda *_: True)
    monkeypatch.setattr(library_lock, "_windows_process_creation_us", lambda _pid: 5_000_000)

    assert library_lock.recover_stale_library_lock(path) is True
    assert not path.exists()


def test_old_windows_lock_is_preserved_for_original_live_process(tmp_path, monkeypatch):
    path = tmp_path / ".natureai-next.lock"
    _write_lock(path, created_at_us=5_000_000)
    monkeypatch.setattr(library_lock.os, "name", "nt")
    monkeypatch.setattr(library_lock.socket, "gethostname", lambda: "Diablo001")
    monkeypatch.setattr(library_lock, "_process_is_alive", lambda *_: True)
    monkeypatch.setattr(library_lock, "_windows_process_creation_us", lambda _pid: 4_000_000)

    assert library_lock.recover_stale_library_lock(path) is False
    assert path.exists()


def test_new_lock_uses_process_start_identity(tmp_path, monkeypatch):
    path = tmp_path / ".natureai-next.lock"
    monkeypatch.setattr(library_lock, "_process_start_id", lambda _pid: "123456")
    lock = library_lock.LibraryLock(path)
    lock.acquire()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["process_start_id"] == "123456"
    finally:
        lock.release()
