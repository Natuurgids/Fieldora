"""Detached GBIF taxonomy database builder; intentionally imports no Qt modules."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from natureai_next.application.dwca_taxonomy import DwcaTaxonomyImportService, _atomic_json


def main() -> int:
    source, workspace, status_name, cancel_name = map(Path, sys.argv[1:5])
    status_name.parent.mkdir(parents=True, exist_ok=True)

    def report(current: int, total: int, message: str) -> None:
        _atomic_json(
            status_name,
            {
                "state": "running",
                "current": current,
                "total": total,
                "message": message,
                "pid": os.getpid(),
            },
        )

    try:
        report(0, 100, "Starting detached GBIF taxonomy builder…")
        result = DwcaTaxonomyImportService().run(
            source, workspace=workspace, progress=report, cancelled=cancel_name.exists
        )
        _atomic_json(
            status_name,
            {
                "state": "ready",
                "current": 100,
                "total": 100,
                "message": "GBIF taxonomy source ready",
                "pid": os.getpid(),
                "source_public_id": result.source_public_id,
                "package_path": str(result.package_path),
                "taxa_count": result.taxa_count,
                "names_count": result.names_count,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return 0
    except InterruptedError:
        _atomic_json(
            status_name,
            {
                "state": "cancelled",
                "current": 0,
                "total": 100,
                "message": "Cancelled at a safe batch boundary",
                "pid": os.getpid(),
            },
        )
        return 2
    except BaseException as exc:
        _atomic_json(
            status_name,
            {
                "state": "failed",
                "current": 0,
                "total": 100,
                "message": "Taxonomy source build failed",
                "error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                "pid": os.getpid(),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
