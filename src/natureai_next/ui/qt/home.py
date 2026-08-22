"""Fieldora role-neutral start screen and operational research overview."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HomeWorkspace(QWidget):
    """A calm start screen focused on work due, evidence, and system state."""

    route_requested = Signal(str)

    def __init__(
        self,
        *,
        library_name: str,
        library_database: Path,
        science_database: Path,
        marine_maritime_database: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._library_name = library_name
        self._library_database = library_database
        self._science_database = science_database
        self._marine_maritime_database = marine_maritime_database
        heading = QLabel(f"<h1>{library_name}</h1>")
        subtitle = QLabel(
            "Your research workspace: continue planned work, review incoming evidence, "
            "and see what needs attention."
        )
        subtitle.setWordWrap(True)
        self._cards = QGridLayout()
        self._upcoming = QListWidget()
        quick = QHBoxLayout()
        for label, route in (
            ("Import data", "Imports"),
            ("Open projects", "Science Projects"),
            ("Research calendar", "Science Calendar"),
            ("AI review", "AI Review"),
            ("Marine science", "Marine & Freshwater Science"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, destination=route: self.route_requested.emit(destination)
            )
            quick.addWidget(button)
        quick.addStretch(1)
        refresh = QPushButton("Refresh overview")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addLayout(self._cards)
        layout.addWidget(QLabel("<h3>Next 30 days</h3>"))
        layout.addWidget(self._upcoming, 1)
        layout.addWidget(QLabel("<h3>Quick actions</h3>"))
        layout.addLayout(quick)
        layout.addWidget(refresh, 0)
        self.refresh()

    @staticmethod
    def _count(database: Path, table: str, where: str = "1=1") -> int:
        if not database.is_file():
            return 0
        try:
            with sqlite3.connect(database) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                if exists is None:
                    return 0
                return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0])
        except sqlite3.Error:
            return 0

    def _card(self, title: str, value: int, route: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        label = QLabel(f"<h2>{value:,}</h2><b>{title}</b>")
        open_button = QPushButton("Open")
        open_button.clicked.connect(
            lambda checked=False, destination=route: self.route_requested.emit(destination)
        )
        layout = QVBoxLayout(frame)
        layout.addWidget(label)
        layout.addWidget(open_button)
        return frame

    def refresh(self) -> None:
        while self._cards.count():
            item = self._cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        values = (
            ("Library assets", self._count(self._library_database, "assets"), "Photos"),
            (
                "Open project tasks",
                self._count(self._science_database, "pm_tasks", "progress < 100"),
                "Science Projects",
            ),
            (
                "Planned activities",
                self._count(self._science_database, "science_activities"),
                "Science Calendar",
            ),
            (
                "Marine records",
                self._count(
                    self._marine_maritime_database,
                    "marine_maritime_records",
                    "domain='marine'",
                ),
                "Marine & Freshwater Science",
            ),
        )
        for index, (title, value, route) in enumerate(values):
            self._cards.addWidget(self._card(title, value, route), index // 4, index % 4)
        self._upcoming.clear()
        today = date.today().isoformat()
        horizon = (date.today() + timedelta(days=30)).isoformat()
        rows: list[tuple[str, str, str]] = []
        if self._science_database.is_file():
            try:
                with sqlite3.connect(self._science_database) as connection:
                    if connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='science_activities'"
                    ).fetchone():
                        rows.extend(
                            (str(day), str(title), "Activity")
                            for day, title in connection.execute(
                                "SELECT activity_date,title FROM science_activities "
                                "WHERE activity_date BETWEEN ? AND ?",
                                (today, horizon),
                            )
                        )
                    if connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pm_tasks'"
                    ).fetchone():
                        rows.extend(
                            (str(day), str(title), "Task")
                            for day, title in connection.execute(
                                "SELECT due_date,title FROM pm_tasks "
                                "WHERE due_date BETWEEN ? AND ? AND progress < 100",
                                (today, horizon),
                            )
                        )
            except sqlite3.Error:
                pass
        for day, title, kind in sorted(rows):
            self._upcoming.addItem(f"{day}  ·  {kind}  ·  {title}")
        if not rows:
            self._upcoming.addItem("No activities or task deadlines in the next 30 days.")
