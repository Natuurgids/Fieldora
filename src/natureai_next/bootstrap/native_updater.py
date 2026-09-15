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

from natureai_next.application.security_install import require_security_install
from natureai_next.application.update_history import UpdateHistoryEntry, UpdateHistoryStore
from natureai_next.application.update_trust import verify_signed_update_index
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.security_install import AuthenticatedReleaseContext, SecurityInstallAcceptanceError
from natureai_next.infrastructure.filesystem.library_lock import recover_stale_library_lock

_SECURITY_INSTALL_SUBJECT = "fieldora-native-updater"
_SECURITY_INSTALL_COMPONENT = "fieldora"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_exit(pid: int, timeout_seconds: float = 120.0, tick: Callable[[], None] | None = None) -> None:
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


def _wait_for_library_unlock(library: Path, timeout_seconds: float = 30.0, tick: Callable[[], None] | None = None) -> None:
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


def _write_status(request_path: Path, payload: dict[str, Any], status: str, detail: str = "") -> None:
    payload["status"] = status
    payload["detail"] = detail
    payload["updated_at_utc"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    temp = request_path.with_suffix(request_path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(request_path)


def _require_trusted_update(payload: dict[str, Any], package: Path, request_path: Path) -> None:
    evidence = payload.get("security_install")
    if not isinstance(evidence, dict):
        raise SecurityInstallAcceptanceError("trusted Security Install evidence is required")
    package_id = str(payload.get("package") or "").strip()
    current_version = str(payload.get("from_version") or "").strip()
    trust_anchor = str(payload.get("trust_anchor_path") or "").strip()
    signed_index_name = str(payload.get("signed_index") or "").strip()
    if not package_id or not current_version or not trust_anchor or not signed_index_name:
        raise SecurityInstallAcceptanceError("native update authenticated release binding is incomplete")
    if Path(signed_index_name).name != signed_index_name:
        raise SecurityInstallAcceptanceError("invalid staged signed-index path")

    verified = verify_signed_update_index(request_path.parent / signed_index_name, Path(trust_anchor))
    signed = verified.payload
    if (
        str(signed.get("package")) != package_id
        or str(signed.get("sha256", "")).casefold() != _sha256(package)
        or int(signed.get("size", -1)) != package.stat().st_size
        or signed.get("security_install") != evidence
    ):
        raise SecurityInstallAcceptanceError("staged update does not match authenticated release metadata")

    paths = resolve_application_paths()
    access_database = paths.subsystem_databases_dir / "access-control.sqlite3"
    require_security_install(
        evidence,
        artifact_path=package,
        access_control_database=access_database,
        subject_id=_SECURITY_INSTALL_SUBJECT,
        expected_package_id=package_id,
        expected_target_component=_SECURITY_INSTALL_COMPONENT,
        actual_target_version=current_version,
        authenticated_release=AuthenticatedReleaseContext(
            release_id=str(signed["release_id"]),
            release_digest=str(signed["release_digest"]),
            signer_key_id=verified.key_id,
        ),
    )


class _ProgressUI:
    def __init__(self, current: str, target: str) -> None:
        self.app = self.window = self.label = self.detail = self.bar = None
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget
        except ImportError:
            return
        self.app = QApplication.instance() or QApplication([])
        self.window = QWidget(); self.window.setWindowTitle("Aperture Maintenance Center"); self.window.setMinimumWidth(520)
        layout = QVBoxLayout(self.window); title = QLabel("<h2>Updating Aperture</h2>"); title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.label = QLabel(f"Version {current} → {target}"); self.detail = QLabel("Preparing update…"); self.detail.setWordWrap(True)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
        for widget in (title, self.label, self.detail, self.bar): layout.addWidget(widget)
        self.window.show(); self.pump()

    def pump(self) -> None:
        if self.app is not None: self.app.processEvents()

    def stage(self, text: str, progress: int) -> None:
        if self.detail is not None: self.detail.setText(text)
        if self.bar is not None: self.bar.setValue(progress)
        self.pump()

    def failure(self, text: str) -> None:
        if self.window is None: return
        from PySide6.QtWidgets import QMessageBox
        self.stage("Update failed", 100); QMessageBox.critical(self.window, "Update failed", f"The previous installation remains available.\n\n{text}")

    def success(self, version: str) -> None:
        self.stage(f"Aperture {version} installed successfully. Launching Aperture…", 100)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline: self.pump(); time.sleep(0.05)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aperture-updater")
    parser.add_argument("--request", required=True, type=Path); parser.add_argument("--parent-pid", required=True, type=int); parser.add_argument("--library", required=True, type=Path)
    args = parser.parse_args(argv); request_path = args.request.resolve(); history_path = args.library.resolve() / "updates" / "update-history.jsonl"; history = UpdateHistoryStore()
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    if payload.get("format") != "natureai-next.pending-update" or payload.get("format_version") != 2: raise ValueError("unsupported staged update request")
    package = request_path.parent / str(payload["package"]); target_version = str(payload["version"]); current_version = str(payload.get("from_version", "current")); ui = _ProgressUI(current_version, target_version)
    if not package.is_file() or package.is_symlink() or _sha256(package) != str(payload["sha256"]).casefold() or package.stat().st_size != int(payload["size"]):
        ui.failure("The staged update package failed verification."); raise ValueError("staged update package verification failed")
    try:
        ui.stage("Authenticating signed release metadata…", 10); _require_trusted_update(payload, package, request_path)
        ui.stage("Update package verified. Waiting for Aperture to close…", 15); _write_status(request_path, payload, "helper-ready"); _write_status(request_path, payload, "waiting-for-exit"); _wait_for_exit(args.parent_pid, tick=ui.pump)
        ui.stage("Aperture closed. Waiting for the library to be released…", 30); _write_status(request_path, payload, "waiting-for-library-unlock"); _wait_for_library_unlock(args.library.resolve(), tick=ui.pump)
        ui.stage("Installing the new Aperture version…", 50); _write_status(request_path, payload, "installing")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(package)], check=False, capture_output=True, text=True)
        (request_path.parent / "update-install.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0: raise RuntimeError(f"package installation failed with exit code {result.returncode}")
        ui.stage("Verifying the installed version…", 80); check = subprocess.run([sys.executable, "-c", "import natureai_next; print(natureai_next.__version__)"], check=False, capture_output=True, text=True)
        if check.returncode != 0 or check.stdout.strip() != target_version: raise RuntimeError("installed version validation failed")
        _write_status(request_path, payload, "installed"); history.append(history_path, UpdateHistoryEntry(version=target_version, status="installed", detail="Update installed and validated")); package.unlink(missing_ok=True); ui.success(target_version)
        aperture = Path(sys.prefix) / "Scripts" / "natureai-next.exe"; restart = [str(aperture)] if aperture.is_file() else [sys.executable, "-m", "natureai_next.bootstrap.cli"]
        subprocess.Popen([*restart, "--library", str(args.library)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True); return 0
    except Exception as exc:
        _write_status(request_path, payload, "failed", str(exc)); history.append(history_path, UpdateHistoryEntry(version=str(payload.get("version", "unknown")), status="failed", detail=str(exc))); ui.failure(str(exc)); return 1


if __name__ == "__main__": raise SystemExit(main())
