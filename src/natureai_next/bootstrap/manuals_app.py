"""Launch the standalone offline Fieldora Manuals application."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit("Fieldora Manuals requires the GUI installation profile") from exc
    from natureai_next.ui.qt.manuals_app import FieldoraManualsWindow

    app = QApplication.instance() or QApplication(list(argv or sys.argv))
    app.setApplicationName("Fieldora Manuals")
    app.setOrganizationName("Fieldora")
    window = FieldoraManualsWindow()
    window.show()
    return app.exec()
