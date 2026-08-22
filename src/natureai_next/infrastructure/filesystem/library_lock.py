"""Exclusive library writer lock with safe stale-owner recovery."""

from __future__ import annotations

import atexit
import contextlib
import ctypes
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LockOwner:
    pid: int
    host: str
    created_at_us: int
    process_start_id: str | None = None


class LibraryLockedError(RuntimeError):
    def __init__(self, path: Path, owner: LockOwner | None = None) -> None:
        self.path = path
        self.owner = owner
        detail = f"library is already locked: {path}"
        if owner is not None:
            detail += f" (pid={owner.pid}, host={owner.host})"
        super().__init__(detail)


def _read_owner(path: Path) -> LockOwner | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return LockOwner(
            pid=int(value["pid"]),
            host=str(value["host"]),
            created_at_us=int(value["created_at_us"]),
            process_start_id=(
                str(value["process_start_id"]) if value.get("process_start_id") else None
            ),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _windows_process_creation_us(pid: int) -> int | None:
    """Return the Windows process creation time as Unix microseconds."""
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        # FILETIME is 100-ns intervals since 1601-01-01 UTC.
        return (creation.value // 10) - 11_644_473_600_000_000
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _process_start_id(pid: int) -> str | None:
    """Return a per-process creation identity that changes when a PID is reused."""
    if os.name == "nt":
        created_us = _windows_process_creation_us(pid)
        return str(created_us) if created_us is not None else None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields_after_name = stat.rsplit(")", 1)[1].split()
        return fields_after_name[19]
    except (OSError, IndexError):
        return None


def _process_is_alive(pid: int, expected_start_id: str | None = None) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    if expected_start_id is not None:
        return _process_start_id(pid) == expected_start_id
    return True


class LibraryLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._held = False

    def acquire(self) -> None:
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "created_at_us": time.time_ns() // 1000,
                "process_start_id": _process_start_id(os.getpid()),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        for _attempt in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                owner = _read_owner(self.path)
                if recover_stale_library_lock(self.path):
                    continue
                raise LibraryLockedError(self.path, owner) from exc
            try:
                os.write(fd, payload.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
            self._held = True
            atexit.register(self.release)
            return
        raise LibraryLockedError(self.path, _read_owner(self.path))

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False
            with contextlib.suppress(Exception):
                atexit.unregister(self.release)

    def __enter__(self) -> LibraryLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def recover_stale_library_lock(path: Path) -> bool:
    """Remove *path* only when it belongs to a dead process on this host.

    Returns ``True`` when the lock is absent or was safely removed.  A live,
    remote, or unreadable owner is never disturbed.
    """
    if not path.exists():
        return True
    owner = _read_owner(path)
    if owner is None:
        return False
    if owner.host.casefold() != socket.gethostname().casefold():
        return False
    if _process_is_alive(owner.pid, owner.process_start_id):
        # Older Windows locks did not record a process-start identity.  A live
        # process with a reused PID must not keep the library locked forever.
        if os.name == "nt" and owner.process_start_id is None:
            created_us = _windows_process_creation_us(owner.pid)
            # A process created after the lock cannot be the lock owner.  Allow
            # a small tolerance for filesystem and clock granularity.
            if created_us is None or created_us <= owner.created_at_us + 2_000_000:
                return False
        else:
            return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True
