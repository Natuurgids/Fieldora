"""Independent GBIF taxonomy browser and library enrichment workspace."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from natureai_next.application.components import ResourceComponentRegistry
from natureai_next.application.external_taxonomy import (
    ExternalTaxon,
    ExternalTaxonomyEnrichmentStore,
    GbifTaxonomyLibrary,
)


class GbifTaxonomyWorkspace(QWidget):
    taxonomy_filter_requested = Signal(str)

    def __init__(
        self,
        *,
        library_database: Path,
        selected_asset_ids,
        component_registry: ResourceComponentRegistry | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._components = component_registry or ResourceComponentRegistry()
        self._source = GbifTaxonomyLibrary()
        self._store = ExternalTaxonomyEnrichmentStore(library_database)
        self._selected_asset_ids = selected_asset_ids
        self._items: list[ExternalTaxon] = []
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Scientific or common name…")
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Scientific name", "Common name", "Rank", "Class", "Order", "Family"]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i in range(2, 6):
            self._table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents
            )
        enrich = QPushButton("Enrich selected library photo(s)")
        enrich.clicked.connect(self._enrich)
        use_filter = QPushButton("Search Library / Collections")
        use_filter.clicked.connect(self._filter)
        refresh = QPushButton("Refresh source")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addWidget(self._search, 1)
        row.addWidget(refresh)
        row.addWidget(enrich)
        row.addWidget(use_filter)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>GBIF Taxonomy</h2>"))
        layout.addWidget(
            QLabel(
                "This view reads the independent GBIF database directly. Aperture stores only asset enrichment links and searchable name snapshots."
            )
        )
        layout.addLayout(row)
        layout.addWidget(self._status)
        layout.addWidget(self._table, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _t: self._timer.start())
        self._search.returnPressed.connect(self.refresh)
        self.refresh()

    def _current(self):
        row = self._table.currentRow()
        return None if row < 0 or row >= len(self._items) else self._items[row]

    @Slot()
    def refresh(self) -> None:
        if not self._components.enabled("gbif"):
            self._items = []
            self._table.setRowCount(0)
            self._status.setText(
                "GBIF taxonomy is disabled under Settings → Resource Components. Installed data has not been removed."
            )
            return
        self._source = GbifTaxonomyLibrary(self._source.root)
        try:
            self._items = list(self._source.search(self._search.text(), limit=300))
            self._table.setRowCount(len(self._items))
            for r, t in enumerate(self._items):
                vals = (
                    t.scientific_name,
                    t.vernacular_name or "",
                    t.rank,
                    t.taxon_class or "",
                    t.taxon_order or "",
                    t.family or "",
                )
                for c, v in enumerate(vals):
                    self._table.setItem(r, c, QTableWidgetItem(v))
            if self._source.database.is_file():
                self._status.setText(
                    f"{len(self._items):,} matching taxa • independent source: {escape(str(self._source.database))}"
                )
            else:
                self._status.setText(
                    "No active GBIF taxonomy database. Import one under Resources → Taxonomy Resources."
                )
        except Exception as exc:
            self._status.setText("GBIF taxonomy unavailable: " + escape(str(exc)))

    @Slot()
    def _enrich(self) -> None:
        if not self._components.enabled("gbif"):
            QMessageBox.information(
                self,
                "GBIF Taxonomy",
                "Enable the GBIF component under Settings → Resource Components first.",
            )
            return
        taxon = self._current()
        assets = tuple(self._selected_asset_ids())
        if taxon is None:
            QMessageBox.information(self, "GBIF Taxonomy", "Select a taxon first.")
            return
        if not assets:
            QMessageBox.information(
                self,
                "GBIF Taxonomy",
                "Select one or more photographs in Library or Collections first.",
            )
            return
        try:
            count = self._store.apply(assets, taxon, source_identity=self._source.identity())
            QMessageBox.information(
                self,
                "Taxonomy enrichment",
                f"Linked {count} photograph(s) to {taxon.scientific_name}. The GBIF database remains separate.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Taxonomy enrichment", str(exc))

    @Slot()
    def _filter(self) -> None:
        taxon = self._current()
        if taxon is None:
            QMessageBox.information(self, "GBIF Taxonomy", "Select a taxon first.")
            return
        self.taxonomy_filter_requested.emit(taxon.scientific_name)
