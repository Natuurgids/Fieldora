"""Verify a NatureAI Next source installation without modifying a library."""

from __future__ import annotations

import argparse
import gc
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import natureai_next
from natureai_next.application.library_service import LibraryService
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend

_REQUIRED_PYTHON: Final = (3, 11)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def _module_check(name: str, required: bool) -> Check:
    available = importlib.util.find_spec(name) is not None
    status = available or not required
    requirement = "required" if required else "optional"
    return Check(name, status, f"{requirement}; {'installed' if available else 'not installed'}")


def _distribution_check(name: str) -> Check:
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return Check(name, False, "distribution not installed")
    return Check(name, True, version)


def _entry_point_path(name: str) -> str | None:
    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    # ``sys.executable`` already lives in ``<venv>/bin`` on POSIX and
    # ``<venv>/Scripts`` on Windows.  Appending another scripts directory made
    # every entry-point check fail for an otherwise valid isolated install.
    # Do not resolve the venv executable symlink: that would move the lookup
    # into the base interpreter's directory instead of the active environment.
    scripts_directory = Path(sys.executable).parent
    candidate = scripts_directory / executable_name
    if candidate.is_file():
        return str(candidate)
    return shutil.which(name)


def _clean_library_schema_check() -> Check:
    """Create and reopen a library using the installed package, then compile core queries."""
    with tempfile.TemporaryDirectory(prefix="aperture-install-check-") as temporary:
        root = Path(temporary) / "Library"
        service = LibraryService(
            SystemClock(),
            SystemUuidGenerator(),
            backend_factory=lambda clock, ids, settings: SqliteLibraryLifecycleBackend(
                clock, ids, settings
            ),
        )
        try:
            with service.open_or_create_clean(root) as opened:
                connection = opened.connection_factory.connect(read_only=True)
                try:
                    required = ("library_info", "assets", "observations", "collections")
                    for table in required:
                        connection.execute(f'SELECT 1 FROM "{table}" LIMIT 0')
                    migration_count = int(
                        connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
                    )
                    quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
                finally:
                    connection.close()
            with service.open(root) as reopened:
                connection = reopened.connection_factory.connect(read_only=True)
                try:
                    connection.execute("SELECT 1 FROM observations LIMIT 0")
                finally:
                    connection.close()
        except (OSError, RuntimeError, sqlite3.DatabaseError) as exc:
            return Check("clean_library_schema", False, f"{type(exc).__name__}: {exc}")
        return Check(
            "clean_library_schema",
            quick.lower() == "ok" and migration_count > 0,
            f"quick_check={quick}; migrations={migration_count}; reopen=ok",
        )


def _science_gui_smoke_check(required: bool) -> Check:
    if importlib.util.find_spec("PySide6") is None:
        return Check("fieldora_science_gui", not required, "PySide6 not installed")
    try:
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from PySide6.QtWidgets import QApplication

        from natureai_next.ui.qt.science import ScienceWorkspace

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(
            prefix="fieldora-science-check-", ignore_cleanup_errors=True
        ) as temporary:
            workspace = ScienceWorkspace(Path(temporary) / "science.sqlite3")
            workspace.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            workspace.close()
            workspace.deleteLater()
            QCoreApplication.sendPostedEvents(
                None, QEvent.Type.DeferredDelete
            )
            application.processEvents()
            del workspace
            gc.collect()
    except Exception as exc:
        return Check("fieldora_science_gui", False, f"{type(exc).__name__}: {exc}")
    return Check("fieldora_science_gui", True, "Science workspace constructed successfully")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-gui", action="store_true")
    parser.add_argument("--require-ai", action="store_true")
    args = parser.parse_args()

    checks = [
        Check("python", sys.version_info[:2] == _REQUIRED_PYTHON, sys.version.replace("\n", " ")),
        Check("natureai_next", bool(natureai_next.__version__), natureai_next.__version__),
        Check(
            "desktop_entry_point",
            _entry_point_path("natureai-next") is not None,
            str(_entry_point_path("natureai-next")),
        ),
        Check(
            "admin_entry_point",
            _entry_point_path("natureai-next-admin") is not None,
            str(_entry_point_path("natureai-next-admin")),
        ),
        Check(
            "resources_entry_point",
            _entry_point_path("natureai-next-resources") is not None,
            str(_entry_point_path("natureai-next-resources")),
        ),
        _distribution_check("Pillow"),
        _distribution_check("cryptography"),
        _module_check("PySide6", args.require_gui),
        _science_gui_smoke_check(args.require_gui),
        _module_check("torch", args.require_ai),
        _module_check("torchvision", args.require_ai),
        _module_check("open_clip", args.require_ai),
        _module_check("hnswlib", args.require_ai),
        _clean_library_schema_check(),
    ]

    cuda: dict[str, object] = {"checked": False}
    if importlib.util.find_spec("torch") is not None:
        import torch

        cuda = {
            "checked": True,
            "torch_version": torch.__version__,
            "available": bool(torch.cuda.is_available()),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }

    report = {
        "application_version": natureai_next.__version__,
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "checks": [asdict(check) for check in checks],
        "cuda": cuda,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(check.passed for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
