"""Native, no-console update and recovery handoff for Windows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class HelperLaunch:
    module: str
    request_path: Path
    parent_pid: int
    library_path: Path


def augment_request(request_path: Path, *, parent_pid: int, library_path: Path) -> None:
    """Add runtime handoff data to an already verified staging request."""
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    payload["parent_pid"] = int(parent_pid)
    payload["library_path"] = str(library_path.resolve())
    temp = request_path.with_suffix(request_path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(request_path)


def launch_helper(launch: HelperLaunch) -> subprocess.Popen[bytes]:
    """Start a detached, purpose-named helper without exposing a console."""
    command = [
        *_helper_command(launch.module),
        "--request",
        str(launch.request_path),
        "--parent-pid",
        str(launch.parent_pid),
        "--library",
        str(launch.library_path),
    ]
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]


def wait_for_helper_ready(
    process: subprocess.Popen[bytes],
    request_path: Path,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    """Wait until the detached helper has verified its request and taken ownership.

    Merely observing a live process is not enough on Windows: a detached pythonw
    process may start and then fail immediately while importing or validating the
    staged request.  The helper therefore writes ``helper-ready`` before the main
    application is allowed to quit.
    """
    deadline = time.monotonic() + timeout_seconds
    last_detail = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                last_detail or f"the native helper exited with code {process.returncode}"
            )
        try:
            payload = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        status = str(payload.get("status", ""))
        last_detail = str(payload.get("detail", ""))
        if status in {"helper-ready", "waiting-for-exit"}:
            return
        if status == "failed":
            raise RuntimeError(last_detail or "the native helper rejected the request")
        time.sleep(0.05)
    raise TimeoutError("the native helper did not acknowledge the update in time")


def _background_python() -> Path:
    current = Path(sys.executable).resolve()
    if os.name == "nt":
        pythonw = current.with_name("pythonw.exe")
        if pythonw.is_file():
            return pythonw
    return current


def _helper_command(module: str) -> tuple[str, ...]:
    aliases = {
        "natureai_next.bootstrap.native_updater": "Aperture Updater.exe",
        "natureai_next.bootstrap.native_recovery": "Aperture Recovery.exe",
    }
    if os.name == "nt" and module in aliases:
        candidate = Path(sys.prefix) / aliases[module]
        if candidate.is_file():
            return str(candidate), "-m", module
    return str(_background_python()), "-m", module
