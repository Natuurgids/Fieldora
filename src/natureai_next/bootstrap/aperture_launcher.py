"""Windowless Windows launcher for the Fieldora desktop application."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from natureai_next.bootstrap.cli import main as cli_main
from natureai_next.bootstrap.launcher_log import write_launcher_log

# Compatibility guard: the shared configuration service resolves
# os.environ.get("APPDATA") and stores data under
# root / "NatureAI" / "NatureAI Next" / "launcher.json".


def _bootstrap_log(status: str, detail: str = "") -> None:
    write_launcher_log("aperture-bootstrap.jsonl", status, detail)


def _configured_library() -> Path | None:
    from natureai_next.application.launcher_configuration import LauncherConfigurationStore

    return LauncherConfigurationStore().load().last_library


def _message_box(message: str, *, error: bool = True) -> None:
    try:
        import ctypes

        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(0, message, "Fieldora", icon)
    except Exception:
        return


def main(argv: Sequence[str] | None = None) -> int:
    _bootstrap_log("process-started")
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if "--library" in forwarded:
        try:
            result = int(cli_main(forwarded))
        except Exception as exc:
            _bootstrap_log("bootstrap-failed", f"{type(exc).__name__}: {exc}")
            return 1
        _bootstrap_log("process-exited", str(result))
        return result
    library = _configured_library()
    if library is None:
        _bootstrap_log("configuration-missing")
        _message_box(
            "No Fieldora Library is configured. Use 'Fieldora - Select Library' and try again."
        )
        return 1
    manifest = library / "library.json"
    database = library / "library.sqlite3"
    has_manifest = manifest.is_file()
    has_database = database.is_file()
    empty_directory = library.is_dir() and not any(library.iterdir())
    missing_directory = not library.exists()
    if has_manifest != has_database or (
        not has_manifest and not empty_directory and not missing_directory
    ):
        _bootstrap_log("library-unavailable", str(library))
        _message_box(
            "The configured folder is not an initialized Fieldora Library and is not empty. "
            "No files were changed. Use 'Fieldora - Select Library' to choose an existing "
            "library or an empty folder for a new V4 library."
        )
        return 1
    try:
        result = int(cli_main(["--library", str(library), "--log-level", "INFO"]))
    except Exception as exc:
        _bootstrap_log("bootstrap-failed", f"{type(exc).__name__}: {exc}")
        _message_box(
            "Fieldora could not start.\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "Use Fieldora (Debug) for diagnostic output."
        )
        return 1
    _bootstrap_log("process-exited", str(result))
    return result
