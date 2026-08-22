"""Detached native library recovery helper. End users never invoke this directly."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_for_exit(pid: int, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise TimeoutError("Aperture did not close in time to restore the library")


def _write_status(
    request_path: Path, payload: dict[str, Any], status: str, detail: str = ""
) -> None:
    payload["status"] = status
    payload["detail"] = detail
    temp = request_path.with_suffix(request_path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(request_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aperture-recovery")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--library", required=True, type=Path)
    args = parser.parse_args(argv)
    request_path = args.request.resolve()
    payload: dict[str, Any] = json.loads(request_path.read_text(encoding="utf-8"))
    if (
        payload.get("format") != "natureai-next.pending-restore"
        or payload.get("format_version") != 1
    ):
        raise ValueError("unsupported staged restore request")
    staged = Path(str(payload["staged_database"])).resolve()
    target = Path(str(payload["target_database"])).resolve()
    emergency = Path(str(payload["emergency_backup"])).resolve()
    if not staged.is_file() or _sha256(staged) != str(payload["sha256"]).casefold():
        raise ValueError("staged backup verification failed")
    if not emergency.is_file():
        raise FileNotFoundError("emergency pre-restore backup is missing")
    rollback = target.with_suffix(target.suffix + ".pre-restore-rollback")
    subsystem_rollbacks: list[tuple[Path, Path]] = []
    try:
        _write_status(request_path, payload, "waiting-for-exit")
        _wait_for_exit(args.parent_pid)
        _write_status(request_path, payload, "restoring")
        shutil.copy2(target, rollback)
        replacement = target.with_suffix(target.suffix + ".restore.tmp")
        shutil.copy2(staged, replacement)
        replacement.replace(target)
        for entry in payload.get("subsystem_databases", []):
            subsystem_staged = Path(str(entry["staged_database"])).resolve()
            subsystem_target = Path(str(entry["target_database"])).resolve()
            if (
                not subsystem_staged.is_file()
                or _sha256(subsystem_staged) != str(entry["sha256"]).casefold()
            ):
                raise ValueError(
                    f"staged subsystem backup verification failed: {entry.get('key')}"
                )
            subsystem_target.parent.mkdir(parents=True, exist_ok=True)
            subsystem_rollback = subsystem_target.with_suffix(
                subsystem_target.suffix + ".pre-restore-rollback"
            )
            if subsystem_target.is_file():
                shutil.copy2(subsystem_target, subsystem_rollback)
                subsystem_rollbacks.append((subsystem_rollback, subsystem_target))
            subsystem_replacement = subsystem_target.with_suffix(
                subsystem_target.suffix + ".restore.tmp"
            )
            shutil.copy2(subsystem_staged, subsystem_replacement)
            subsystem_replacement.replace(subsystem_target)
        _write_status(request_path, payload, "restored")
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
        if rollback.is_file():
            shutil.copy2(rollback, target)
        for subsystem_rollback, subsystem_target in subsystem_rollbacks:
            if subsystem_rollback.is_file():
                shutil.copy2(subsystem_rollback, subsystem_target)
        _write_status(request_path, payload, "failed", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
