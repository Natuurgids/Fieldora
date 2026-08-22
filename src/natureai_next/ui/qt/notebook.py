"""Offline rich-text field notebook workspace linked to Library assets."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

try:
    from PySide6.QtCore import Qt, QTimer, Signal, Slot
    from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextListFormat
    from PySide6.QtWidgets import (
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


@dataclass
class NotebookPage:
    public_id: str
    title: str = "Untitled note"
    body: str = ""  # searchable plain-text projection and legacy compatibility
    body_html: str = ""
    tags: list[str] = field(default_factory=list)
    taxon: str = ""
    location: str = ""
    asset_public_ids: list[str] = field(default_factory=list)
    created_at_utc: str = ""
    updated_at_utc: str = ""


class NotebookStore:
    """Small, atomic, library-local JSON store; no network dependency."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[NotebookPage]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            pages: list[NotebookPage] = []
            for raw in payload.get("pages", []):
                item = dict(raw)
                item.setdefault("body_html", "")
                pages.append(NotebookPage(**item))
            return pages
        except Exception:
            return []

    def save(self, pages: list[NotebookPage]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".partial")
        temporary.write_text(
            json.dumps(
                {"version": 2, "pages": [asdict(page) for page in pages]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


class NotebookWorkspace(QWidget):
    """Field notebook with rich text, autosave, and Library asset links."""

    status_changed = Signal(str)

    def __init__(
        self,
        *,
        store_path: Path,
        selected_asset_ids: Callable[[], tuple[str, ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = NotebookStore(store_path)
        self._selected_asset_ids = selected_asset_ids
        self._pages = self._store.load()
        self._current_id: str | None = None
        self._loading = False

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search notebook…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_list)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._page_selected)

        new_button = QPushButton("New note")
        new_button.clicked.connect(self.new_page)
        selection_button = QPushButton("New from Library selection")
        selection_button.clicked.connect(self.new_from_selection)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_page)

        left_header = QHBoxLayout()
        left_header.addWidget(new_button)
        left_header.addWidget(selection_button)
        left_header.addWidget(delete_button)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Notebook"))
        left_layout.addWidget(self._search)
        left_layout.addLayout(left_header)
        left_layout.addWidget(self._list, 1)

        self._title = QLineEdit()
        self._body = QTextEdit()
        self._body.setAcceptRichText(True)
        self._body.setPlaceholderText(
            "Field observations, behaviour, habitat, identification notes…"
        )
        self._tags = QLineEdit()
        self._tags.setPlaceholderText("Comma-separated tags")
        self._taxon = QLineEdit()
        self._taxon.setPlaceholderText("Taxon or working identification")
        self._location = QLineEdit()
        self._location.setPlaceholderText("Location")
        self._assets = QListWidget()
        self._assets.setMinimumHeight(110)

        rich_toolbar = QHBoxLayout()
        for label, callback in (
            ("B", self._toggle_bold),
            ("I", self._toggle_italic),
            ("U", self._toggle_underline),
            ("• List", self._bullet_list),
            ("1. List", self._numbered_list),
            ("Quote", self._quote_block),
            ("Clear format", self._clear_formatting),
        ):
            button = QPushButton(label)
            button.setMaximumWidth(92)
            button.clicked.connect(callback)
            rich_toolbar.addWidget(button)
        self._style = QComboBox()
        self._style.addItems(["Paragraph", "Heading 1", "Heading 2", "Heading 3"])
        self._style.currentIndexChanged.connect(self._apply_block_style)
        rich_toolbar.addWidget(self._style)
        rich_toolbar.addStretch(1)

        attach_button = QPushButton("Attach selected Library images")
        attach_button.clicked.connect(self.attach_selection)
        detach_button = QPushButton("Remove selected links")
        detach_button.clicked.connect(self.detach_assets)
        save_button = QPushButton("Save now")
        save_button.clicked.connect(self.save_current)
        self._status = QLabel("Autosave enabled")

        metadata = QFormLayout()
        metadata.addRow("Title", self._title)
        metadata.addRow("Taxonomy", self._taxon)
        metadata.addRow("Location", self._location)
        metadata.addRow("Tags", self._tags)

        actions = QHBoxLayout()
        actions.addWidget(attach_button)
        actions.addWidget(detach_button)
        actions.addStretch(1)
        actions.addWidget(self._status)
        actions.addWidget(save_button)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addLayout(metadata)
        right_layout.addWidget(QLabel("Notes"))
        right_layout.addLayout(rich_toolbar)
        right_layout.addWidget(self._body, 3)
        right_layout.addWidget(QLabel("Linked images"))
        right_layout.addWidget(self._assets, 1)
        right_layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([330, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(650)
        self._save_timer.timeout.connect(self.save_current)
        for widget in (self._title, self._tags, self._taxon, self._location):
            widget.textChanged.connect(self._schedule_save)
        self._body.textChanged.connect(self._schedule_save)

        self._refresh_list()
        if self._pages:
            self._select_page(self._pages[0].public_id)
        else:
            self.new_page()

    @Slot()
    def _schedule_save(self) -> None:
        if not self._loading and self._current_id:
            self._status.setText("Unsaved changes")
            self._save_timer.start()

    @Slot()
    def _refresh_list(self) -> None:
        selected = self._current_id
        query = self._search.text().strip().casefold()
        self._list.blockSignals(True)
        self._list.clear()
        selected_item: QListWidgetItem | None = None
        for page in sorted(self._pages, key=lambda item: item.updated_at_utc, reverse=True):
            haystack = " ".join(
                (page.title, page.body, " ".join(page.tags), page.taxon, page.location)
            ).casefold()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(page.title or "Untitled note")
            item.setData(Qt.ItemDataRole.UserRole, page.public_id)
            item.setToolTip(f"{len(page.asset_public_ids)} linked image(s)")
            self._list.addItem(item)
            if page.public_id == selected:
                selected_item = item
        if selected_item is not None:
            self._list.setCurrentItem(selected_item)
        self._list.blockSignals(False)

    def _find(self, public_id: str | None) -> NotebookPage | None:
        return next((page for page in self._pages if page.public_id == public_id), None)

    def _select_page(self, public_id: str) -> None:
        """Select and load a page even when list-rebuild signals were suppressed."""
        for row in range(self._list.count()):
            item = self._list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == public_id:
                self._list.setCurrentItem(item)
                self._load_page(public_id)
                return
        self._load_page(public_id)

    def _load_page(self, public_id: str | None) -> None:
        page = self._find(public_id)
        self._current_id = public_id
        self._loading = True
        try:
            self._title.setText(page.title if page else "")
            if page and page.body_html:
                self._body.setHtml(page.body_html)
            else:
                self._body.setPlainText(page.body if page else "")
            self._tags.setText(", ".join(page.tags) if page else "")
            self._taxon.setText(page.taxon if page else "")
            self._location.setText(page.location if page else "")
            self._assets.clear()
            if page:
                for asset_id in page.asset_public_ids:
                    item = QListWidgetItem(asset_id)
                    item.setData(Qt.ItemDataRole.UserRole, asset_id)
                    self._assets.addItem(item)
        finally:
            self._loading = False
        self._status.setText("Autosave enabled")

    @Slot(object, object)
    def _page_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        # Read the clicked page identity before saving. Saving normally rebuilds
        # the sorted list and can invalidate ``current`` or restore the previous
        # row, which made notebook rows appear impossible to select.
        public_id = str(current.data(Qt.ItemDataRole.UserRole)) if current else None
        self._save_current(refresh_list=False)
        self._load_page(public_id)

    @Slot()
    def new_page(self) -> None:
        self.save_current()
        now = datetime.now(UTC).isoformat()
        page = NotebookPage(public_id=str(uuid4()), created_at_utc=now, updated_at_utc=now)
        self._pages.append(page)
        self._store.save(self._pages)
        self._current_id = page.public_id
        self._search.clear()
        self._refresh_list()
        self._select_page(page.public_id)
        self._title.setFocus(Qt.FocusReason.OtherFocusReason)
        self._title.selectAll()

    @Slot()
    def new_from_selection(self) -> None:
        selected = self._selected_asset_ids()
        self.new_page()
        if selected:
            page = self._find(self._current_id)
            if page is not None:
                page.asset_public_ids = list(dict.fromkeys(selected))
                self._load_page(page.public_id)
                self._title.setText(
                    f"Field note — {len(selected)} selected image{'s' if len(selected) != 1 else ''}"
                )
        else:
            QMessageBox.information(self, "Notebook", "Select one or more images in Library first.")

    @Slot()
    def attach_selection(self) -> None:
        page = self._find(self._current_id)
        if page is None:
            return
        selected = self._selected_asset_ids()
        if not selected:
            QMessageBox.information(self, "Notebook", "Select one or more images in Library first.")
            return
        existing = set(page.asset_public_ids)
        page.asset_public_ids.extend(asset_id for asset_id in selected if asset_id not in existing)
        self._load_page(page.public_id)
        self._schedule_save()

    @Slot()
    def detach_assets(self) -> None:
        page = self._find(self._current_id)
        if page is None:
            return
        remove = {str(item.data(Qt.ItemDataRole.UserRole)) for item in self._assets.selectedItems()}
        page.asset_public_ids = [
            asset_id for asset_id in page.asset_public_ids if asset_id not in remove
        ]
        self._load_page(page.public_id)
        self._schedule_save()

    @Slot()
    def save_current(self) -> None:
        self._save_current(refresh_list=True)

    def _save_current(self, *, refresh_list: bool) -> None:
        if self._loading:
            return
        page = self._find(self._current_id)
        if page is None:
            return
        page.title = self._title.text().strip() or "Untitled note"
        page.body = self._body.toPlainText()
        page.body_html = self._body.toHtml()
        page.tags = [value.strip() for value in self._tags.text().split(",") if value.strip()]
        page.taxon = self._taxon.text().strip()
        page.location = self._location.text().strip()
        page.updated_at_utc = datetime.now(UTC).isoformat()
        self._store.save(self._pages)
        self._status.setText("Saved")
        self.status_changed.emit("Notebook saved")
        if refresh_list:
            self._refresh_list()

    @Slot()
    def delete_page(self) -> None:
        page = self._find(self._current_id)
        if page is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete notebook page",
                f"Delete ‘{page.title}’?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._pages = [item for item in self._pages if item.public_id != page.public_id]
        self._current_id = None
        self._store.save(self._pages)
        self._refresh_list()
        if self._list.count():
            first_id = str(self._list.item(0).data(Qt.ItemDataRole.UserRole))
            self._select_page(first_id)
        else:
            self.new_page()

    def _merge_char_format(self, char_format: QTextCharFormat) -> None:
        cursor = self._body.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(char_format)
        self._body.mergeCurrentCharFormat(char_format)
        self._body.setFocus()

    @Slot()
    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(
            QFont.Weight.Normal
            if self._body.fontWeight() > QFont.Weight.Normal
            else QFont.Weight.Bold
        )
        self._merge_char_format(fmt)

    @Slot()
    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._body.fontItalic())
        self._merge_char_format(fmt)

    @Slot()
    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._body.fontUnderline())
        self._merge_char_format(fmt)

    @Slot()
    def _bullet_list(self) -> None:
        self._body.textCursor().createList(QTextListFormat.Style.ListDisc)
        self._body.setFocus()

    @Slot()
    def _numbered_list(self) -> None:
        self._body.textCursor().createList(QTextListFormat.Style.ListDecimal)
        self._body.setFocus()

    @Slot()
    def _quote_block(self) -> None:
        cursor = self._body.textCursor()
        block = cursor.blockFormat()
        block.setLeftMargin(28.0 if block.leftMargin() < 20.0 else 0.0)
        cursor.mergeBlockFormat(block)
        self._body.setFocus()

    @Slot()
    def _clear_formatting(self) -> None:
        cursor = self._body.textCursor()
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt)
        block = QTextBlockFormat()
        cursor.setBlockFormat(block)
        self._body.setCurrentCharFormat(fmt)
        self._body.setFocus()

    @Slot(int)
    def _apply_block_style(self, index: int) -> None:
        if self._loading:
            return
        sizes = (10.0, 20.0, 16.0, 13.0)
        weights = (QFont.Weight.Normal, QFont.Weight.Bold, QFont.Weight.Bold, QFont.Weight.DemiBold)
        cursor = self._body.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontPointSize(sizes[max(0, min(index, len(sizes) - 1))])
        fmt.setFontWeight(weights[max(0, min(index, len(weights) - 1))])
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(fmt)
        self._body.mergeCurrentCharFormat(fmt)
        self._body.setFocus()
