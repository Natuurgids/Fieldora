"""Detached native update helper with a visible Aperture progress window."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from natureai_next.application.update_history import UpdateHistoryEntry, UpdateHistoryStore
from natureai_next.infrastructure.filesystem.library_lock import recover_stale_library_lock


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_exit(
    pid: int, timeout_seconds: float = 120.0, tick: Callable[[], None] | None = None
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        if tick is not None:
            tick()
        time.sleep(0.25)
    raise TimeoutError("Aperture did not close in time to install the update")


def _wait_for_library_unlock(
    library: Path, timeout_seconds: float = 30.0, tick: Callable[[], None] | None = None
) -> None:
    lock_path = library / ".natureai-next.lock"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not lock_path.exists():
            return
        if recover_stale_library_lock(lock_path):
            return
        if tick is not None:
            tick()
        time.sleep(0.1)
    raise TimeoutError("Aperture closed but the library lock was not released")


def _write_status(
    request_path: Path, payload: dict[str, Any], status: str, detail: str = ""
) -> None:
    payload["status"] = status
    payload["detail"] = detail
    payload["updated_at_utc"] = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )
    temp = request_path.with_suffix(request_path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(request_path)


class _ProgressUI:
    """Small optional Qt progress window; falls back cleanly in headless environments."""

    def __init__(self, current: str, target: str) -> None:
        self.app = None
        self.window = None
        self.label = None
        self.detail = None
        self.bar = None
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget
        except ImportError:
            return
        self.app = QApplication.instance() or QApplication([])
        self.window = QWidget()
        self.window.setWindowTitle("Aperture Maintenance Center")
        self.window.setMinimumWidth(520)
        layout = QVBoxLayout(self.window)
        title = QLabel("<h2>Updating Aperture</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.label = QLabel(f"Version {current} → {target}")
        self.detail = QLabel("Preparing update…")
        self.detail.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(title)
        layout.addWidget(self.label)
        layout.addWidget(self.detail)
        layout.addWidget(self.bar)
        self.window.show()
        self.pump()

    def pump(self) -> None:
        if self.app is not None:
            self.app.processEvents()

    def stage(self, text: str, progress: int) -> None:
        if self.detail is not None:
            self.detail.setText(text)
        if self.bar is not None:
            self.bar.setValue(progress)
        self.pump()

    def failure(self, text: str) -> None:
        if self.window is None:
            return
        from PySide6.QtWidgets import QMessageBox

        self.stage("Update failed", 100)
        QMessageBox.critical(
            self.window, "Update failed", f"The previous installation remains available.\n\n{text}"
        )

    def success(self, version: str) -> None:
        self.stage(f"Aperture {version} installed successfully. Launching Aperture…", 100)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            self.pump()
            time.sleep(0.05)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aperture-updater")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--library", required=True, type=Path)
    args = parser.parse_args(argv)
    request_path = args.request.resolve()
    history_path = args.library.resolve() / "updates" / "update-history.jsonl"
    history = UpdateHistoryStore()
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    if (
        payload.get("format") != "natureai-next.pending-update"
        or payload.get("format_version") != 1
    ):
        raise ValueError("unsupported staged update request")
    package = request_path.parent / str(payload["package"])
    target_version = str(payload["version"])
    current_version = str(payload.get("from_version", "current"))
    ui = _ProgressUI(current_version, target_version)
    if not package.is_file() or _sha256(package) != str(payload["sha256"]).casefold():
        ui.failure("The staged update package failed checksum verification.")
        raise ValueError("staged update package verification failed")
    try:
        ui.stage("Update package verified. Waiting for Aperture to close…", 15)
        _write_status(request_path, payload, "helper-ready")
        _write_status(request_path, payload, "waiting-for-exit")
        _wait_for_exit(args.parent_pid, tick=ui.pump)
        ui.stage("Aperture closed. Waiting for the library to be released…", 30)
        _write_status(request_path, payload, "waiting-for-library-unlock")
        _wait_for_library_unlock(args.library.resolve(), tick=ui.pump)
        ui.stage("Installing the new Aperture version…", 50)
        _write_status(request_path, payload, "installing")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                str(package),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        log_path = request_path.parent / "update-install.log"
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"package installation failed with exit code {result.returncode}")
        ui.stage("Verifying the installed version…", 80)
        check = subprocess.run(
            [sys.executable, "-c", "import natureai_next; print(natureai_next.__version__)"],
            check=False,
            capture_output=True,
            text=True,
        )
        if check.returncode != 0 or check.stdout.strip() != target_version:
            raise RuntimeError("installed version validation failed")
        _write_status(request_path, payload, "installed")
        history.append(
            history_path,
            UpdateHistoryEntry(
                version=target_version, status="installed", detail="Update installed and validated"
            ),
        )
        package.unlink(missing_ok=True)
        ui.success(target_version)
        aperture = Path(sys.prefix) / "Scripts" / "natureai-next.exe"
        restart = (
            [str(aperture)]
            if aperture.is_file()
            else [sys.executable, "-m", "natureai_next.bootstrap.cli"]
        )
        subprocess.Popen(
            [*restart, "--library", str(args.library)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return 0
    except Exception as exc:
        _write_status(request_path, payload, "failed", str(exc))
        history.append(
            history_path,
            UpdateHistoryEntry(
                version=str(payload.get("version", "unknown")), status="failed", detail=str(exc)
            ),
        )
        ui.failure(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
