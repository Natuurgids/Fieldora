"""Working-set filter dialog for the isolated taxonomy source database."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from natureai_next.application.taxonomy_sources import TaxonomySourceLibrary, TaxonomyWorkingSet


class TaxonomyWorkingSetDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Taxonomy working set")
        self.resize(520, 320)
        self.library = TaxonomySourceLibrary()
        self.name = QLineEdit()
        self.kingdom = QComboBox()
        self.taxon_class = QComboBox()
        self.taxon_order = QComboBox()
        self.family = QComboBox()
        self.rank = QComboBox()
        for box in (self.kingdom, self.taxon_class, self.taxon_order, self.family, self.rank):
            box.addItem("All", None)
        self._fill(self.kingdom, "kingdom", {})
        self._fill(self.rank, "rank", {})
        self.kingdom.currentIndexChanged.connect(self._refresh_class)
        self.taxon_class.currentIndexChanged.connect(self._refresh_order)
        self.taxon_order.currentIndexChanged.connect(self._refresh_family)
        form = QFormLayout()
        form.addRow("Set name", self.name)
        form.addRow("Kingdom", self.kingdom)
        form.addRow("Class", self.taxon_class)
        form.addRow("Order / subgroup", self.taxon_order)
        form.addRow("Family", self.family)
        form.addRow("Rank", self.rank)
        self.count_label = QLabel("Choose filters to calculate the working set.")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<b>Create a reusable taxonomy view</b><br>Example: Animalia → Aves → Accipitriformes for birds of prey. The GBIF source remains read-only."
            )
        )
        layout.addLayout(form)
        layout.addWidget(self.count_label)
        layout.addWidget(buttons)
        self._refresh_class()

    def _fill(self, box, field, filters) -> None:
        for value in self.library.distinct(field, filters):
            box.addItem(value, value)

    def _reset(self, box) -> None:
        box.blockSignals(True)
        box.clear()
        box.addItem("All", None)
        box.blockSignals(False)

    def _filters(self):
        return {
            "kingdom": self.kingdom.currentData(),
            "taxon_class": self.taxon_class.currentData(),
            "taxon_order": self.taxon_order.currentData(),
            "family": self.family.currentData(),
            "rank": self.rank.currentData(),
        }

    def _refresh_class(self) -> None:
        self._reset(self.taxon_class)
        self._fill(self.taxon_class, "taxon_class", {"kingdom": self.kingdom.currentData()})
        self._refresh_order()

    def _refresh_order(self) -> None:
        self._reset(self.taxon_order)
        self._fill(
            self.taxon_order,
            "taxon_order",
            {"kingdom": self.kingdom.currentData(), "taxon_class": self.taxon_class.currentData()},
        )
        self._refresh_family()

    def _refresh_family(self) -> None:
        self._reset(self.family)
        self._fill(
            self.family,
            "family",
            {
                "kingdom": self.kingdom.currentData(),
                "taxon_class": self.taxon_class.currentData(),
                "taxon_order": self.taxon_order.currentData(),
            },
        )
        self._show_count()

    def _working_set(self):
        return TaxonomyWorkingSet(self.name.text().strip(), **self._filters())

    def _show_count(self) -> None:
        try:
            self.count_label.setText(f"Matching taxa: {self.library.count(self._working_set()):,}")
        except Exception as exc:
            self.count_label.setText(f"Count unavailable: {exc}")

    def _save(self) -> None:
        item = self._working_set()
        if not item.name:
            QMessageBox.warning(self, "Taxonomy working set", "Enter a name for this set.")
            return
        self.library.save_set(item)
        self.accept()
