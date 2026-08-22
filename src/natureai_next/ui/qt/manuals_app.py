"""Standalone, searchable offline manuals application for Fieldora."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


@dataclass(frozen=True, slots=True)
class Manual:
    manual_id: str
    title: str
    filename: str
    audience: str


MANUALS = (
    Manual(
        "installation",
        "Installation Manual",
        "installation.md",
        "Installers and deployment engineers",
    ),
    Manual(
        "administrator",
        "Administrator Manual",
        "administrator.md",
        "System, security, and data administrators",
    ),
    Manual(
        "user",
        "User Manual",
        "user.md",
        "Researchers and collection teams",
    ),
)


def manuals_root() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "manuals"


def manual_text(manual: Manual) -> str:
    path = manuals_root() / manual.filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            f"# {manual.title}\n\nThis manual is unavailable in the current "
            f"installation.\n\nExpected file: `{path}`"
        )


class FieldoraManualsWindow(QMainWindow):
    """Independent offline manuals browser using the Fieldora help interaction model."""

    def __init__(self, *, initial_manual: str = "user") -> None:
        super().__init__()
        self.setWindowTitle("Fieldora Manuals")
        self.resize(1120, 760)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search all Fieldora manuals")
        self._search.setAccessibleName("Search Fieldora manuals")
        self._manuals = QListWidget(self)
        self._manuals.setAccessibleName("Fieldora manuals")
        self._browser = QTextBrowser(self)
        self._browser.setAccessibleName("Manual content")
        self._browser.setOpenExternalLinks(False)
        for manual in MANUALS:
            item = QListWidgetItem(f"{manual.title}\n{manual.audience}")
            item.setData(Qt.ItemDataRole.UserRole, manual.manual_id)
            self._manuals.addItem(item)
        self._search.textChanged.connect(self._search_all)
        self._manuals.currentItemChanged.connect(self._show_current)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Fieldora 5.4.0 manuals</b>"))
        left.addWidget(self._search)
        left.addWidget(self._manuals, 1)
        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addWidget(self._browser, 3)
        central = QWidget(self)
        central.setLayout(body)
        self.setCentralWidget(central)
        self.open_manual(initial_manual)

    def _manual(self, manual_id: str) -> Manual:
        for manual in MANUALS:
            if manual.manual_id == manual_id:
                return manual
        raise KeyError(manual_id)

    def _show_current(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        manual_id = current.data(Qt.ItemDataRole.UserRole)
        if manual_id is not None:
            self._browser.setMarkdown(manual_text(self._manual(str(manual_id))))

    def _search_all(self, text: str) -> None:
        needle = text.casefold().strip()
        if not needle:
            current = self._manuals.currentItem()
            self._show_current(current, None)
            return
        matches = []
        for manual in MANUALS:
            for line in manual_text(manual).splitlines():
                if needle in line.casefold():
                    matches.append(f"### {manual.title}\n\n{line.strip()}")
                    if len(matches) >= 100:
                        break
            if len(matches) >= 100:
                break
        self._browser.setMarkdown(
            f"# Search results\n\n**Query:** {text}\n\n"
            + ("\n\n---\n\n".join(matches) if matches else "No matches found.")
        )

    def open_manual(self, manual_id: str) -> None:
        for row in range(self._manuals.count()):
            item = self._manuals.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == manual_id:
                self._manuals.setCurrentItem(item)
                return
        self._manuals.setCurrentRow(0)
