"""Qt Knowledge Center over reference taxonomy and local observation history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from html import escape

from natureai_next.application.knowledge_center import (
    KnowledgeCenterService,
    KnowledgeCenterTaxonPage,
)
from natureai_next.application.knowledge_engine import KnowledgeEngine, TaxonKnowledgeDossier

try:
    from PySide6.QtCore import Qt, Signal, Slot
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
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


class KnowledgeCenterWorkspace(QWidget):
    """Searchable taxon reference pages enriched with active-library evidence."""

    observation_history_requested = Signal(str)

    def __init__(
        self,
        service_factory: Callable[[], KnowledgeCenterService],
        knowledge_engine_factory: Callable[[], KnowledgeEngine] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_factory = service_factory
        self._knowledge_engine_factory = knowledge_engine_factory
        self._service: KnowledgeCenterService | None = None
        self._knowledge_engine: KnowledgeEngine | None = None
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search scientific or common name…")
        self._language = QLineEdit()
        self._language.setPlaceholderText("Language (for example en, bg)")
        self._region = QLineEdit()
        self._region.setPlaceholderText("Region (for example BG, NL)")
        self._search.returnPressed.connect(self.search)
        self._results = QListWidget()
        self._results.currentItemChanged.connect(self._selection_changed)
        self._page = QTextBrowser()
        self._page.setOpenExternalLinks(True)
        self._status = QLabel("Reference taxonomy activates when searched.")
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search)
        preferences_button = QPushButton("Apply names")
        preferences_button.clicked.connect(self._apply_preferences)
        self._open_history = QPushButton("Open observation history")
        self._open_history.setEnabled(False)
        self._open_history.clicked.connect(self._request_history)

        bar = QHBoxLayout()
        bar.addWidget(self._search, 1)
        bar.addWidget(search_button)
        preferences = QHBoxLayout()
        preferences.addWidget(self._language, 1)
        preferences.addWidget(self._region, 1)
        preferences.addWidget(preferences_button)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addLayout(bar)
        ll.addLayout(preferences)
        ll.addWidget(self._results, 1)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(self._page, 1)
        rl.addWidget(self._open_history)
        rl.addWidget(self._status)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        title = QLabel("Knowledge Center")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(split, 1)
        self._page.setHtml(
            "<h2>Reference knowledge and local evidence</h2><p>Search an installed taxonomy dataset to open a taxon page.</p>"
        )

    def _service_instance(self) -> KnowledgeCenterService:
        if self._service is None:
            self._service = self._service_factory()
        return self._service

    def _knowledge_engine_instance(self) -> KnowledgeEngine | None:
        if self._knowledge_engine_factory is None:
            return None
        if self._knowledge_engine is None:
            self._knowledge_engine = self._knowledge_engine_factory()
        return self._knowledge_engine

    @staticmethod
    def _date(value: int | None) -> str:
        if value is None:
            return "—"
        return datetime.fromtimestamp(value / 1_000_000, tz=UTC).strftime("%Y-%m-%d")

    @Slot()
    def _apply_preferences(self) -> None:
        try:
            service = self._service_instance()
            taxonomy = getattr(service, "_taxonomy", None)
            setter = getattr(taxonomy, "set_preferences", None)
            if setter is None:
                self._status.setText("This taxonomy source does not support name preferences.")
                return
            from time import time_ns

            setter(
                language_tag=self._language.text().strip() or None,
                region_code=self._region.text().strip() or None,
                prefer_common_name=True,
                updated_at_us=time_ns() // 1000,
            )
            self._status.setText("Name language and region preferences applied.")
            if self._search.text().strip():
                self.search()
        except Exception as exc:
            self._status.setText(str(exc))

    @Slot()
    def search(self) -> None:
        text = self._search.text().strip()
        self._results.clear()
        if not text:
            self._status.setText("Enter a scientific or common name.")
            return
        try:
            cards = self._service_instance().search(text, limit=200)
        except Exception as exc:
            self._status.setText(str(exc))
            return
        for card in cards:
            label = card.preferred_name or card.scientific_name
            item = QListWidgetItem(
                f"{label}  ·  {card.scientific_name}  ·  {card.observation_count} local"
            )
            item.setData(Qt.ItemDataRole.UserRole, card.public_id)
            self._results.addItem(item)
        if self._results.count():
            self._results.setCurrentRow(0)
        self._status.setText(f"{len(cards)} taxon result(s)")

    def show_taxon(self, public_id: str, *, local_identity: bool = False) -> None:
        try:
            service = self._service_instance()
            page = (
                service.taxon_page_for_local_taxon(public_id)
                if local_identity
                else service.taxon_page(public_id)
            )
        except Exception as exc:
            self._status.setText(str(exc))
            return
        self._render(page)

    @Slot(object, object)
    def _selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is not None:
            self.show_taxon(str(current.data(Qt.ItemDataRole.UserRole)))

    def _render(self, page: KnowledgeCenterTaxonPage) -> None:
        ref = page.reference
        names = ", ".join(escape(x) for x in ref.preferred_names) or "—"
        facts = (
            "".join(
                f"<li><b>{escape(str(x.get('fact_type', 'fact')))}:</b> {escape(str(x.get('value_text', '')))} <small>({escape(str(x.get('source', '')))} )</small></li>"
                for x in ref.facts
            )
            or "<li>No reference facts installed.</li>"
        )
        dist = (
            "".join(
                f"<li>{escape(str(x.get('region_code', '')))} — {escape(str(x.get('occurrence_status') or 'recorded'))} <small>({escape(str(x.get('source', '')))} )</small></li>"
                for x in ref.distributions
            )
            or "<li>No distribution records installed.</li>"
        )
        history = page.observation_history
        local_id = None if history is None else history.summary.taxon_public_id
        dossier: TaxonKnowledgeDossier | None = None
        engine = self._knowledge_engine_instance()
        if engine is not None:
            dossier = engine.taxon_dossier(ref.public_id, observation_taxon_public_id=local_id)
        if history is None:
            local = "<p>No confirmed observations are linked in this library.</p>"
        else:
            s = history.summary
            local = (
                f"<p><b>{s.observation_count}</b> confirmed observations · <b>{s.evidence_photo_count}</b> evidence photographs<br>"
                f"First: {self._date(s.first_observed_at_us)} · Last: {self._date(s.last_observed_at_us)}<br>Countries: {escape(', '.join(s.country_codes) or '—')}</p>"
            )
        evidence = ""
        if dossier is not None:
            score = dossier.evidence
            reasons = "".join(f"<li>{escape(reason)}</li>" for reason in score.reasons)
            evidence = (
                f"<h3>Evidence summary</h3><p><b>Evidence score:</b> {score.score:.0%}<br>"
                f"Verified observation ratio: {score.verified_observation_ratio:.0%}</p><ul>{reasons}</ul>"
            )
        self._page.setHtml(
            f"<h2>{escape(ref.scientific_name)}</h2><p>{escape(ref.authorship or '')}<br><b>Rank:</b> {escape(ref.rank)} · <b>Status:</b> {escape(ref.status)}<br><b>Names:</b> {names}</p><h3>Local evidence</h3>{local}{evidence}<h3>Knowledge facts</h3><ul>{facts}</ul><h3>Distribution</h3><ul>{dist}</ul>"
        )
        self._open_history.setProperty("taxon_public_id", local_id)
        self._open_history.setEnabled(local_id is not None)
        self._status.setText(
            "Local evidence is synthesized at read time; reference and library records remain separate."
        )

    @Slot()
    def _request_history(self) -> None:
        value = self._open_history.property("taxon_public_id")
        if value:
            self.observation_history_requested.emit(str(value))
