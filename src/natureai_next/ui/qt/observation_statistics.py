"""Personal life lists and observation statistics workspace."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from natureai_next.application.observation_intelligence import ObservationIntelligenceService

try:
    from PySide6.QtCore import Qt, QTimer, Slot
    from PySide6.QtWidgets import (
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class ObservationStatisticsWorkspace(QWidget):
    """Live projections derived from human-confirmed observations."""

    def __init__(
        self, *, service: ObservationIntelligenceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._species = QLabel("0")
        self._observations = QLabel("0")
        self._photos = QLabel("0")
        self._countries = QLabel("0")
        self._first_year = QLabel("0")
        for label in (
            self._species,
            self._observations,
            self._photos,
            self._countries,
            self._first_year,
        ):
            label.setStyleSheet("font-size: 24px; font-weight: 600;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards = QGridLayout()
        for col, (title, value) in enumerate(
            (
                ("Species", self._species),
                ("Observations", self._observations),
                ("Evidence photos", self._photos),
                ("Countries", self._countries),
                ("First observations this year", self._first_year),
            )
        ):
            box = QWidget()
            layout = QVBoxLayout(box)
            heading = QLabel(title)
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(heading)
            layout.addWidget(value)
            cards.addWidget(box, 0, col)
        self._life = QTableWidget(0, 4)
        self._life.setHorizontalHeaderLabels(
            ("Biological group", "Species", "Observations", "Photos")
        )
        self._life.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._life.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._top = QListWidget()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        title = QLabel("Life Lists & Observation Statistics")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        layout.addLayout(cards)
        body = QHBoxLayout()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Personal life list by biological group"))
        ll.addWidget(self._life)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Most observed species"))
        rl.addWidget(self._top)
        body.addWidget(left, 2)
        body.addWidget(right, 1)
        layout.addLayout(body, 1)
        layout.addWidget(refresh)
        QTimer.singleShot(0, self._initial_refresh)

    def _initial_refresh(self) -> None:
        try:
            self.refresh()
        except Exception:
            logging.getLogger(__name__).exception("Observation statistics initial refresh failed")
            self._top.clear()
            self._top.addItem(
                QListWidgetItem(
                    "Observation statistics could not be loaded. See the diagnostic log."
                )
            )

    @Slot()
    def refresh(self) -> None:
        stats = self._service.statistics(current_year=datetime.now(UTC).year)
        self._species.setText(str(stats.species_count))
        self._observations.setText(str(stats.observation_count))
        self._photos.setText(str(stats.evidence_photo_count))
        self._countries.setText(str(stats.country_count))
        self._first_year.setText(str(stats.first_observations_this_year))
        self._life.setRowCount(len(stats.life_list))
        for row, entry in enumerate(stats.life_list):
            for col, value in enumerate(
                (
                    entry.group_name,
                    entry.species_count,
                    entry.observation_count,
                    entry.evidence_photo_count,
                )
            ):
                self._life.setItem(row, col, QTableWidgetItem(str(value)))
        self._life.resizeColumnsToContents()
        self._top.clear()
        for rank, item in enumerate(stats.most_observed_species, 1):
            self._top.addItem(
                QListWidgetItem(
                    f"{rank}. {item.scientific_name} — {item.observation_count} observation(s)"
                )
            )
        if not stats.most_observed_species:
            empty = QListWidgetItem("No confirmed observations yet.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._top.addItem(empty)
