"""User-facing observation history and species dashboard workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from natureai_next.application.knowledge_engine import KnowledgeEngine
from natureai_next.application.observation_intelligence import ObservationIntelligenceService
from natureai_next.domain.observation_intelligence import (
    SpeciesObservationHistory,
    SpeciesObservationSummary,
)

try:
    from PySide6.QtCore import QSize, Qt, Signal, Slot
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSplitter,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class ObservationHistoryWorkspace(QWidget):
    """Species dashboard with history, timeline, and evidence gallery."""

    viewer_requested = Signal(object, str)
    knowledge_requested = Signal(str)

    def __init__(
        self,
        *,
        service: ObservationIntelligenceService,
        thumbnails: object,
        ecology_service: object | None = None,
        knowledge_engine: KnowledgeEngine | None = None,
        enrichment_controller: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._knowledge_engine = knowledge_engine
        self._thumbnails = thumbnails
        self._ecology_service = ecology_service
        self._species_by_id: dict[str, SpeciesObservationSummary] = {}
        self._current_history: SpeciesObservationHistory | None = None
        self._enrichment_panel = None

        self._species = QListWidget()
        self._species.currentItemChanged.connect(self._species_changed)
        self._summary = QTextBrowser()
        self._country_filter = QComboBox()
        self._country_filter.currentIndexChanged.connect(self._apply_filters)
        self._collection_filter = QComboBox()
        self._collection_filter.currentIndexChanged.connect(self._apply_filters)
        self._seasonality = QLabel("Monthly observations")
        self._seasonality.setWordWrap(True)
        self._related = QListWidget()
        self._related.setMaximumHeight(110)
        self._related.itemDoubleClicked.connect(self._related_opened)
        self._timeline_label = QLabel("Observation timeline — 0 entries")
        self._timeline = QListWidget()
        self._timeline.setMinimumHeight(180)
        self._timeline.setAlternatingRowColors(True)
        self._timeline.currentRowChanged.connect(self._timeline_changed)
        self._gallery = QListWidget()
        self._gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self._gallery.setIconSize(QSize(180, 135))
        self._gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._gallery.setMovement(QListWidget.Movement.Static)
        self._gallery.itemDoubleClicked.connect(self._open_photo)
        self._status = QLabel("Ready")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self._knowledge_button = QPushButton("Open in Knowledge Center")
        self._knowledge_button.setEnabled(False)
        self._knowledge_button.clicked.connect(self._open_knowledge)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Confirmed species"))
        left_layout.addWidget(self._species, 1)
        left_layout.addWidget(refresh)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._summary)
        right_layout.addWidget(self._knowledge_button)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Country"))
        filters.addWidget(self._country_filter)
        filters.addWidget(QLabel("Collection"))
        filters.addWidget(self._collection_filter)
        filters.addStretch(1)
        right_layout.addLayout(filters)
        right_layout.addWidget(self._seasonality)
        right_layout.addWidget(QLabel("Related taxa — double-click to open"))
        right_layout.addWidget(self._related)
        right_layout.addWidget(self._timeline_label)
        right_layout.addWidget(self._timeline, 1)
        right_layout.addWidget(QLabel("Evidence photographs — double-click to open Viewer"))
        right_layout.addWidget(self._gallery, 2)
        if enrichment_controller is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType
            from natureai_next.ui.qt.enrichment import CanonicalEnrichmentPanel

            self._enrichment_panel = CanonicalEnrichmentPanel(
                enrichment_controller, SubjectRef(SubjectType.OBSERVATION, "__none__"), self
            )
            right_layout.addWidget(QLabel("Accepted observation evidence"))
            right_layout.addWidget(self._enrichment_panel, 2)
        right_layout.addWidget(self._status)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        title = QLabel("Species Dashboard & Observation History")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(splitter, 1)
        self.refresh()

    @staticmethod
    def _date(value: int | None) -> str:
        if value is None:
            return "—"
        return datetime.fromtimestamp(value / 1_000_000, tz=UTC).strftime("%Y-%m-%d")

    @Slot()
    def refresh(self) -> None:
        selected = self.current_taxon_public_id()
        try:
            summaries = (
                self._knowledge_engine.observation_species(limit=2000)
                if self._knowledge_engine is not None
                else self._service.list_species(limit=2000)
            )
        except Exception as exc:
            self._status.setText(str(exc))
            return
        self._species.clear()
        self._species_by_id.clear()
        for summary in summaries:
            self._species_by_id[summary.taxon_public_id] = summary
            item = QListWidgetItem(
                f"{summary.scientific_name}  ·  {summary.observation_count} obs  ·  {summary.evidence_photo_count} photos"
            )
            item.setData(Qt.ItemDataRole.UserRole, summary.taxon_public_id)
            self._species.addItem(item)
            if summary.taxon_public_id == selected:
                self._species.setCurrentItem(item)
        if self._species.currentRow() < 0 and self._species.count():
            self._species.setCurrentRow(0)
        if not summaries:
            self._summary.setHtml(
                "<h2>No confirmed observations yet</h2><p>Accept taxonomy in AI Review to create your personal observation history.</p>"
            )
            self._timeline.clear()
            self._timeline_label.setText("Observation timeline — 0 entries")
            self._gallery.clear()
        self._status.setText(f"{len(summaries)} confirmed species")

    def current_taxon_public_id(self) -> str | None:
        item = self._species.currentItem()
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def show_taxon(self, taxon_public_id: str) -> None:
        for row in range(self._species.count()):
            item = self._species.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == taxon_public_id:
                self._species.setCurrentRow(row)
                return
        self.refresh()

    @Slot(object, object)
    def _species_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        taxon_id = str(current.data(Qt.ItemDataRole.UserRole))
        try:
            history = (
                self._knowledge_engine.observation_history(taxon_id)
                if self._knowledge_engine is not None
                else self._service.history_for_taxon(taxon_id)
            )
        except Exception as exc:
            self._status.setText(str(exc))
            return
        self._current_history = history
        self._knowledge_button.setEnabled(True)
        self._populate_filters(history)
        summary = history.summary
        countries = ", ".join(summary.country_codes) or "—"
        ecology = (
            None if self._ecology_service is None else self._ecology_service.for_taxon(taxon_id)
        )
        ecology_html = "<h3>Ecological context</h3><p>No local ecological context is installed for this species.</p>"
        if ecology is not None:
            months = set(getattr(ecology, "seasonal_months", ()))
            month_names = (
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            )
            season = " ".join(
                f"<b>{name}</b>" if index in months else f"<span style='color:#888'>{name}</span>"
                for index, name in enumerate(month_names, 1)
            )
            habitats = ", ".join(getattr(ecology, "habitats", ())) or "—"
            source = (
                " / ".join(
                    filter(
                        None,
                        (
                            getattr(ecology, "source_name", None),
                            getattr(ecology, "source_version", None),
                        ),
                    )
                )
                or "—"
            )
            ecology_html = (
                "<h3>Conservation, seasonality & habitat</h3>"
                f"<p><b>Conservation:</b> {getattr(ecology, 'conservation_status', None) or '—'}<br>"
                f"<b>Migration:</b> {getattr(ecology, 'migration_status', None) or '—'}<br>"
                f"<b>Habitats:</b> {habitats}<br><b>Source:</b> {source}</p>"
                f"<p><b>Seasonal presence:</b><br>{season}</p>"
            )
        self._summary.setHtml(
            f"<h2>{summary.scientific_name}</h2>"
            f"<p><b>Rank:</b> {summary.rank or '—'}<br>"
            f"<b>Confirmed observations:</b> {summary.observation_count}<br>"
            f"<b>Supporting photographs:</b> {summary.evidence_photo_count}<br>"
            f"<b>First observed:</b> {self._date(summary.first_observed_at_us)}<br>"
            f"<b>Last observed:</b> {self._date(summary.last_observed_at_us)}<br>"
            f"<b>Countries:</b> {countries}</p>" + ecology_html
        )
        self._update_monthly_chart(history, ecology)
        self._related.clear()
        try:
            related = (
                self._knowledge_engine.related_taxa(taxon_id, limit=8)
                if self._knowledge_engine is not None
                else self._service.related_taxa(taxon_id, limit=8)
            )
        except Exception:
            related = ()
        for related_id, related_name, related_rank in related:
            item = QListWidgetItem(
                f"{related_name}" + (f" · {related_rank}" if related_rank else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, related_id)
            self._related.addItem(item)
        if not related:
            empty = QListWidgetItem("No related accepted taxa found in the installed taxonomy.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._related.addItem(empty)
        self._apply_filters()

    def _populate_filters(self, history: SpeciesObservationHistory) -> None:
        country = self._country_filter.currentData()
        collection = self._collection_filter.currentData()
        countries = sorted({entry.country_code for entry in history.timeline if entry.country_code})
        collections = sorted(
            {
                name
                for entry in history.timeline
                for photo in entry.photos
                for name in photo.collection_names
            }
        )
        self._country_filter.blockSignals(True)
        self._country_filter.clear()
        self._country_filter.addItem("All countries", None)
        for value in countries:
            self._country_filter.addItem(value, value)
        self._country_filter.blockSignals(False)
        self._collection_filter.blockSignals(True)
        self._collection_filter.clear()
        self._collection_filter.addItem("All collections", None)
        for value in collections:
            self._collection_filter.addItem(value, value)
        self._collection_filter.blockSignals(False)
        for combo, wanted in (
            (self._country_filter, country),
            (self._collection_filter, collection),
        ):
            idx = combo.findData(wanted)
            combo.setCurrentIndex(max(0, idx))

    @Slot()
    def _apply_filters(self) -> None:
        history = self._current_history
        if history is None:
            return
        country = self._country_filter.currentData()
        collection = self._collection_filter.currentData()
        entries = []
        for entry in history.timeline:
            if country and entry.country_code != country:
                continue
            names = {name for photo in entry.photos for name in photo.collection_names}
            if collection and collection not in names:
                continue
            entries.append(entry)
        self._timeline.clear()
        self._timeline_label.setText(
            f"Observation timeline — {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
        )
        for entry in entries:
            names = sorted({name for photo in entry.photos for name in photo.collection_names})
            details = [entry.country_code or "No country", f"{len(entry.photos)} photo(s)"]
            if names:
                details.append(", ".join(names[:3]))
            item = QListWidgetItem(
                f"{self._date(entry.observed_at_us)}  ·  " + "  ·  ".join(details)
            )
            item.setData(Qt.ItemDataRole.UserRole, entry.observation_public_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry)
            self._timeline.addItem(item)
        if self._timeline.count():
            self._timeline.setCurrentRow(0)
            self._timeline_changed(0)
        else:
            self._gallery.clear()
            empty = QListWidgetItem(
                "No confirmed timeline entries are available for the selected filters."
            )
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._timeline.addItem(empty)

    def _update_monthly_chart(
        self, history: SpeciesObservationHistory, ecology: object | None
    ) -> None:
        counts = [0] * 12
        for entry in history.timeline:
            month = datetime.fromtimestamp(entry.observed_at_us / 1_000_000, tz=UTC).month
            counts[month - 1] += 1
        expected = set(getattr(ecology, "seasonal_months", ()) if ecology is not None else ())
        names = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        cells = []
        for i, (name, count) in enumerate(zip(names, counts, strict=False), 1):
            marker = "expected" if i in expected else "outside" if expected else "unknown"
            cells.append(f"{name}: {'█' * min(count, 8) or '·'} {count} ({marker})")
        self._seasonality.setText("Personal observations vs expected season\n" + "   ".join(cells))

    @Slot()
    def _open_knowledge(self) -> None:
        taxon_id = self.current_taxon_public_id()
        if taxon_id:
            self.knowledge_requested.emit(taxon_id)

    @Slot(object)
    def _related_opened(self, item: QListWidgetItem) -> None:
        taxon_id = item.data(Qt.ItemDataRole.UserRole)
        if taxon_id:
            self.show_taxon(str(taxon_id))

    @Slot(int)
    def _timeline_changed(self, row: int) -> None:
        self._gallery.clear()
        history = self._current_history
        if history is None or row < 0:
            return
        item = self._timeline.item(row)
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole + 1)
        if entry is None:
            return
        if self._enrichment_panel is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            self._enrichment_panel.set_subject(
                SubjectRef(SubjectType.OBSERVATION, entry.observation_public_id)
            )
        for photo in entry.photos:
            path = Path(photo.primary_path) if photo.primary_path else None
            cached = Path(photo.thumbnail_path) if photo.thumbnail_path else None
            icon = QIcon()
            try:
                data = self._thumbnails.load(source_path=path, cached_path=cached, max_size=256)
                pixmap = QPixmap()
                if data and pixmap.loadFromData(data):
                    icon = QIcon(pixmap)
            except Exception:
                pass
            name = path.name if path else photo.asset_public_id
            collections = ", ".join(photo.collection_names)
            text = name + (f"\n{collections}" if collections else "")
            item = QListWidgetItem(icon, text)
            item.setData(Qt.ItemDataRole.UserRole, photo.asset_public_id)
            self._gallery.addItem(item)
        self._status.setText(
            f"Observation {entry.observation_public_id} · {len(entry.photos)} evidence photograph(s)"
        )

    @Slot(object)
    def _open_photo(self, item: QListWidgetItem) -> None:
        asset_id = str(item.data(Qt.ItemDataRole.UserRole))
        history = self._current_history
        if history is None:
            return
        ordered = tuple(
            photo.asset_public_id for entry in history.timeline for photo in entry.photos
        )
        if asset_id in ordered:
            self.viewer_requested.emit(ordered, asset_id)
