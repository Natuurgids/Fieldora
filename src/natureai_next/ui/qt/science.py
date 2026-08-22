"""Local-first scientific project planning, whiteboard and activity calendar.

The active repository collections supersede the removed legacy SQL tables:
``science_artifacts``, ``science_dossiers``, ``science_dossier_media``,
``science_project_stages``, ``science_project_resources``, ``science_project_budgets``,
``science_board_shapes``, ``science_whiteboards``, ``science_whiteboard_elements`` and
``science_dossier_whiteboards``. The repository configures ``PRAGMA busy_timeout=5000``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from natureai_next.domain.science import ScienceRevision, ScienceRevisionConflict
from natureai_next.application.science import (
    ScienceSession,
    default_science_snapshot,
)
from natureai_next.application.science_packages import PortableProjectService
from natureai_next.application.calendar_interop import CalendarEvent, CalendarInteropService
from natureai_next.application.excalidraw_documents import OfflineExcalidrawDocuments
from natureai_next.domain.science_packages import ProjectCollisionPolicy
from natureai_next.infrastructure.database.science import SqliteScienceRepository
from natureai_next.ui.qt.excalidraw_editor import EmbeddedExcalidrawEditor
from natureai_next.ui.qt.project_management import ProjectManagementWorkspace
from natureai_next.application.project_management import ProjectManagementService
from natureai_next.application.workspace_context import WorkspaceContext
from natureai_next.application.local_profiles import LocalProfileStore
from natureai_next.ui.qt.activity_calendar import ActivityCountCalendar

from natureai_next.ui.qt.date_time_input import get_datetime_text

from PySide6.QtCore import QByteArray, QDate, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DrawingCanvas(QGraphicsView):
    """Small local-first sketch surface with select, pen, line and shape tools."""

    def __init__(
        self,
        scene: QGraphicsScene,
        shape_created: Callable[[dict], None],
        positions_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(scene)
        self._shape_created = shape_created
        self._positions_changed = positions_changed
        self._tool = "select"
        self._color = "#263238"
        self._start = None
        self._path: QPainterPath | None = None

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == "select" else QGraphicsView.DragMode.NoDrag
        )

    def set_color(self, color: str) -> None:
        self._color = color

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._tool == "select":
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        self._start = point
        if self._tool == "pen":
            self._path = QPainterPath(point)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._tool == "pen" and self._path is not None:
            point = self.mapToScene(event.position().toPoint())
            self._path.lineTo(point)
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._tool == "select":
            super().mouseReleaseEvent(event)
            if self._positions_changed is not None:
                self._positions_changed()
            return
        if self._start is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        end = self.mapToScene(event.position().toPoint())
        if self._tool == "pen" and self._path is not None:
            points = [
                [self._path.elementAt(index).x, self._path.elementAt(index).y]
                for index in range(self._path.elementCount())
            ]
            if len(points) > 1:
                self._shape_created(
                    {"id": str(uuid4()), "kind": "pen", "points": points, "color": self._color}
                )
        elif self._tool in {"line", "rectangle", "ellipse"}:
            self._shape_created(
                {
                    "id": str(uuid4()), "kind": self._tool,
                    "x1": self._start.x(), "y1": self._start.y(),
                    "x2": end.x(), "y2": end.y(), "color": self._color,
                }
            )
        self._start = None
        self._path = None
        event.accept()


class ScienceWorkspace(QWidget):
    """Fieldora-owned offline science hub inspired by open-source research tools."""

    route_requested = Signal(str)

    def __init__(
        self,
        storage_path: Path,
        selected_asset_ids: Callable[[], tuple[str, ...]] = tuple,
        section: str = "projects",
        science_session: ScienceSession | None = None,
        library_database_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = storage_path
        self._selected_asset_ids = selected_asset_ids
        self._library_database_path = library_database_path
        resolved_path = storage_path.resolve()
        self._resolved_path = resolved_path
        self._repository = SqliteScienceRepository(
            storage_path, default_science_snapshot
        )
        self._science_session = science_session or ScienceSession(self._repository)
        self._data = self._science_session.data
        self._portable_projects = PortableProjectService(self._science_session)
        self._project_service = ProjectManagementService(storage_path)
        self._workspace_context = WorkspaceContext.current()
        self._unsubscribe_workspace_context = self._workspace_context.subscribe(self._workspace_context_event)
        self._excalidraw = OfflineExcalidrawDocuments(storage_path.parent / "Documents")
        legacy_path = storage_path.with_name("science-workspace.json")
        if legacy_path.exists() and not any(
            self._data[key] for key in ("projects", "board", "activities", "artifacts")
        ):
            try:
                legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
                for key in ("projects", "board", "activities"):
                    if isinstance(legacy.get(key), list):
                        self._data[key] = legacy[key]
                self._save()
            except (OSError, ValueError, TypeError):
                pass
        title = QLabel(f"<h2>{section.replace('_', ' ').title()}</h2>")
        subtitle = QLabel(
            "Plan research, develop ideas visually, and coordinate field and analysis work. "
            "All Science data stays in Fieldora's separate Science database."
        )
        subtitle.setWordWrap(True)
        pages = {
            "projects": (self._project_management_page, "Project & Work Management"),
            "dossiers": (self._dossiers_page, "Dossiers"),
            "whiteboard": (self._whiteboard_page, "Whiteboards"),
            "calendar": (self._calendar_page, "Research Calendar"),
            "animals": (lambda: self._artifact_page("animal"), "Animals"),
            "plants": (lambda: self._artifact_page("plant"), "Plants & Fungi"),
            "other_artifacts": (
                lambda: self._artifact_page("other"), "Other Specimens & Artifacts",
            ),
        }
        if section not in pages:
            raise ValueError(f"unknown Science section: {section}")
        page_factory, page_title = pages[section]
        self._tabs = QTabWidget(self)
        self._tabs.addTab(page_factory(), page_title)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._tabs, 1)
        if hasattr(self, "_project_table"):
            self._refresh_projects()
        self._refresh_board()
        self._refresh_calendar()
        self._refresh_artifacts()

    def closeEvent(self, event: object) -> None:
        """Release process-wide subscriptions before Qt destroys child widgets.

        The workspace context keeps strong references to subscribed bound methods.
        Without explicit unsubscription, a closed Science workspace can remain alive
        long enough to keep its temporary SQLite database open on Windows.
        """
        unsubscribe = getattr(self, "_unsubscribe_workspace_context", None)
        if unsubscribe is not None:
            unsubscribe()
            self._unsubscribe_workspace_context = None
        super().closeEvent(event)

    def _project_management_page(self) -> QWidget:
        """Return the replacement project module.

        The work-management schema is intentionally independent from the legacy
        Science project snapshot. Existing lightweight project rows are not
        migrated because this release establishes a new task domain.
        """
        self._project_management = ProjectManagementWorkspace(
            self._path,
            selected_asset_ids=self._selected_asset_ids,
            library_database_path=self._library_database_path,
            parent=self,
        )
        self._project_management.route_requested.connect(self.route_requested.emit)
        return self._project_management

    def select_project(self, project_id: str, *, research_area: bool = False) -> bool:
        workspace = getattr(self, "_project_management", None)
        return bool(workspace and workspace.select_project(project_id, research_area=research_area))

    def _default(self) -> dict:
        return default_science_snapshot()

    def _load(self) -> dict:
        snapshot, revision = self._repository.load_snapshot()
        self._loaded_revision = revision.database_revision
        return snapshot


    def _save(self) -> None:
        self._science_session.save()
        return


    def _projects_page(self) -> QWidget:
        page = QWidget()
        self._project_table = QTableWidget(0, 5)
        self._project_table.setHorizontalHeaderLabels(
            ("Project", "Status", "Lead", "Start", "Due")
        )
        self._project_table.itemChanged.connect(self._project_changed)
        self._project_table.itemSelectionChanged.connect(self._refresh_project_details)
        self._project_table.horizontalHeader().setStretchLastSection(True)
        add = QPushButton("New Project")
        add.clicked.connect(self._add_project)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove_project)
        export_project = QPushButton("Export Project Package")
        export_project.clicked.connect(self._export_project_package)
        import_project = QPushButton("Import Project Package")
        import_project.clicked.connect(self._import_project_package)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(export_project)
        buttons.addWidget(import_project)
        buttons.addStretch(1)
        self._stage_table = QTableWidget(0, 3)
        self._stage_table.setHorizontalHeaderLabels(("Stage", "Status", "Notes"))
        self._activity_table = QTableWidget(0, 4)
        self._activity_table.setHorizontalHeaderLabels(("Activity", "Stage", "Due", "Status"))
        self._resource_table = QTableWidget(0, 4)
        self._resource_table.setHorizontalHeaderLabels(("Resource", "Quantity", "Unit", "Unit cost"))
        add_stage = QPushButton("Add Stage")
        add_stage.clicked.connect(self._add_project_stage)
        add_activity = QPushButton("Add Activity")
        add_activity.clicked.connect(self._add_project_activity)
        add_resource = QPushButton("Add Resource")
        add_resource.clicked.connect(self._add_project_resource)
        budget = QPushButton("Set Budget")
        budget.clicked.connect(self._set_project_budget)
        detail_buttons = QHBoxLayout()
        for button in (add_stage, add_activity, add_resource, budget):
            detail_buttons.addWidget(button)
        detail_buttons.addStretch(1)
        self._budget_label = QLabel("Select a project to manage its plan and budget.")
        details = QTabWidget()
        details.addTab(self._stage_table, "Stages")
        details.addTab(self._activity_table, "Activities")
        details.addTab(self._resource_table, "Resources")
        layout = QVBoxLayout(page)
        layout.addLayout(buttons)
        layout.addWidget(self._project_table)
        layout.addLayout(detail_buttons)
        layout.addWidget(self._budget_label)
        layout.addWidget(details)
        return page

    def _selected_project(self) -> dict | None:
        if not hasattr(self, "_project_table"):
            return None
        row = self._project_table.currentRow()
        projects = self._data.get("projects", [])
        return projects[row] if 0 <= row < len(projects) else None

    def _add_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New science project", "Project name")
        if not accepted or not name.strip():
            return
        project_id = str(uuid4())
        self._data["projects"].append(
            {
                "id": project_id,
                "name": name.strip(),
                "status": "Planned",
                "lead": "",
                "start": date.today().isoformat(),
                "due": "",
            }
        )
        for order, title in enumerate(
            (
                "Preparation", "Research location A", "Research location B",
                "Consolidation of information", "Write thesis",
            ),
            start=1,
        ):
            self._data["project_stages"].append(
                {
                    "id": str(uuid4()), "project_id": project_id, "title": title,
                    "status": "Planned", "order": order, "notes": "",
                }
            )
        self._data["project_budgets"].append(
            {"project_id": project_id, "currency": "EUR", "planned": 0.0, "spent": 0.0}
        )
        self._save()
        self._refresh_projects()

    def _remove_project(self) -> None:
        row = self._project_table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
            self,
            "Remove project",
            "Remove the selected project, its dossiers, planning records, and "
            "whiteboards not used by another dossier? Library media will not be deleted.",
        ) != QMessageBox.StandardButton.Yes:
            return
        project_id = self._data["projects"][row]["id"]
        del self._data["projects"][row]
        dossier_ids = {
            dossier["id"] for dossier in self._data["dossiers"]
            if dossier.get("project_id") == project_id or dossier["id"] == project_id
        }
        linked_board_ids = {
            link["board_id"] for link in self._data["dossier_whiteboards"]
            if link["dossier_id"] in dossier_ids
        }
        self._data["dossiers"] = [
            dossier for dossier in self._data["dossiers"]
            if dossier["id"] not in dossier_ids
        ]
        self._data["dossier_whiteboards"] = [
            link for link in self._data["dossier_whiteboards"]
            if link["dossier_id"] not in dossier_ids
        ]
        still_linked_boards = {
            link["board_id"] for link in self._data["dossier_whiteboards"]
        }
        removable_boards = linked_board_ids - still_linked_boards
        self._data["whiteboards"] = [
            board for board in self._data["whiteboards"]
            if board["id"] not in removable_boards
        ]
        self._data["whiteboard_elements"] = [
            element for element in self._data["whiteboard_elements"]
            if element["board_id"] not in removable_boards
        ]
        for key in ("project_stages", "project_activities", "project_resources"):
            self._data[key] = [
                item for item in self._data[key] if item["project_id"] != project_id
            ]
        self._data["project_budgets"] = [
            item for item in self._data["project_budgets"]
            if item["project_id"] != project_id
        ]
        self._save()
        self._refresh_projects()
        self._refresh_dossiers()
        self._refresh_board_picker()
        self._refresh_board()

    def _export_project_package(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        include_references = QMessageBox.question(
            self,
            "Include Library references?",
            "Include stable references to linked photos, sounds, videos, and documents?\n\n"
            "Original media files are never included in this package.",
        ) == QMessageBox.StandardButton.Yes
        suggested = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in project["name"]
        ).strip("-") or "fieldora-project"
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Export portable Fieldora project",
            f"{suggested}.fieldora-project.zip",
            "Fieldora project packages (*.fieldora-project.zip *.zip)",
        )
        if not destination:
            return
        try:
            summary = self._portable_projects.export_project(
                project["id"],
                Path(destination),
                include_library_references=include_references,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Project export failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Project package created",
            f"Project: {summary.project_name}\n"
            f"Records: {summary.record_count}\n"
            f"Library references: {summary.library_reference_count}\n"
            "Original media included: No\n"
            f"SHA-256: {summary.package_sha256}",
        )

    def _import_project_package(self) -> None:
        source, _filter = QFileDialog.getOpenFileName(
            self,
            "Import portable Fieldora project",
            "",
            "Fieldora project packages (*.fieldora-project.zip *.zip)",
        )
        if not source:
            return
        policy_label, accepted = QInputDialog.getItem(
            self,
            "Collision handling",
            "When an incoming record already exists",
            (
                "Stop without changing anything",
                "Keep existing records",
                "Replace existing records",
            ),
            0,
            False,
        )
        if not accepted:
            return
        policy = {
            "Stop without changing anything": ProjectCollisionPolicy.FAIL,
            "Keep existing records": ProjectCollisionPolicy.SKIP,
            "Replace existing records": ProjectCollisionPolicy.REPLACE,
        }[policy_label]
        try:
            plan = self._portable_projects.plan_import(Path(source), policy=policy)
        except Exception as exc:
            QMessageBox.critical(self, "Invalid project package", str(exc))
            return
        preview = (
            f"Project: {plan.summary.project_name}\n"
            f"Records: {plan.summary.record_count}\n"
            f"Library references: {plan.summary.library_reference_count}\n"
            f"Original media included: {'Yes' if plan.summary.includes_originals else 'No'}\n"
            f"Collisions: {len(plan.collisions)}\n"
            f"SHA-256: {plan.summary.package_sha256}\n\n"
            "Apply this import?"
        )
        if not plan.can_apply:
            QMessageBox.warning(
                self, "Import blocked",
                preview + "\n\nChoose a collision policy that can resolve collisions.",
            )
            return
        if QMessageBox.question(
            self, "Import project preview", preview
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._portable_projects.import_project(Path(source), policy=policy)
        except Exception as exc:
            QMessageBox.critical(
                self, "Project import failed",
                f"No partial import was retained.\n\n{exc}",
            )
            return
        self._refresh_projects()
        self._refresh_project_details()
        self._refresh_dossiers()
        self._refresh_board_picker()
        self._refresh_board()
        QMessageBox.information(self, "Project imported", "Import completed successfully.")

    def _project_changed(self, item: QTableWidgetItem) -> None:
        keys = ("name", "status", "lead", "start", "due")
        projects = self._data.get("projects", [])
        if 0 <= item.row() < len(projects):
            projects[item.row()][keys[item.column()]] = item.text().strip()
            self._save()

    def _refresh_projects(self) -> None:
        if not hasattr(self, "_project_table"):
            return
        projects = self._data.get("projects", [])
        self._project_table.blockSignals(True)
        self._project_table.setRowCount(len(projects))
        for row, project in enumerate(projects):
            for column, key in enumerate(("name", "status", "lead", "start", "due")):
                self._project_table.setItem(
                    row, column, QTableWidgetItem(str(project.get(key, "")))
                )
        self._project_table.blockSignals(False)
        if projects and self._project_table.currentRow() < 0:
            self._project_table.selectRow(0)
        self._refresh_project_details()

    def _add_project_stage(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        title, accepted = QInputDialog.getText(self, "Project stage", "Stage name")
        if not accepted or not title.strip():
            return
        stages = [r for r in self._data["project_stages"] if r["project_id"] == project["id"]]
        self._data["project_stages"].append(
            {
                "id": str(uuid4()), "project_id": project["id"], "title": title.strip(),
                "status": "Planned", "order": len(stages) + 1, "notes": "",
            }
        )
        self._save()
        self._refresh_project_details()

    def _add_project_activity(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        title, accepted = QInputDialog.getText(self, "Project activity", "Activity")
        if not accepted or not title.strip():
            return
        stages = [r for r in self._data["project_stages"] if r["project_id"] == project["id"]]
        names = ["No stage"] + [r["title"] for r in stages]
        stage_name, accepted = QInputDialog.getItem(
            self, "Activity stage", "Stage", names, 0, False
        )
        if not accepted:
            return
        due, accepted = get_datetime_text(
            self, "Activity due date", "Due date", value=project.get("due") or None, include_time=False
        )
        if not accepted:
            return
        stage = next((r for r in stages if r["title"] == stage_name), None)
        self._data["project_activities"].append(
            {
                "id": str(uuid4()), "project_id": project["id"],
                "stage_id": stage["id"] if stage else None, "title": title.strip(),
                "due": due.strip(), "status": "Planned",
            }
        )
        self._save()
        self._refresh_project_details()

    def _add_project_resource(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        name, accepted = QInputDialog.getText(
            self, "Needed resource", "Resource (camera, bat detector, measuring tool…)"
        )
        if not accepted or not name.strip():
            return
        quantity, accepted = QInputDialog.getDouble(
            self, "Resource quantity", "Quantity", 1.0, 0.0, 1_000_000.0, 2
        )
        if not accepted:
            return
        unit, accepted = QInputDialog.getText(self, "Resource unit", "Unit", text="item")
        if not accepted:
            return
        unit_cost, accepted = QInputDialog.getDouble(
            self, "Estimated cost", "Unit cost", 0.0, 0.0, 1_000_000_000.0, 2
        )
        if not accepted:
            return
        self._data["project_resources"].append(
            {
                "id": str(uuid4()), "project_id": project["id"], "name": name.strip(),
                "quantity": quantity, "unit": unit.strip(), "unit_cost": unit_cost,
            }
        )
        self._save()
        self._refresh_project_details()

    def _set_project_budget(self) -> None:
        project = self._selected_project()
        if project is None:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        existing = next(
            (r for r in self._data["project_budgets"] if r["project_id"] == project["id"]),
            {"currency": "EUR", "planned": 0.0, "spent": 0.0},
        )
        currency, accepted = QInputDialog.getText(
            self, "Project budget", "Currency", text=str(existing["currency"])
        )
        if not accepted:
            return
        planned, accepted = QInputDialog.getDouble(
            self, "Project budget", "Planned budget", float(existing["planned"]),
            0.0, 1_000_000_000.0, 2,
        )
        if not accepted:
            return
        spent, accepted = QInputDialog.getDouble(
            self, "Project budget", "Spent to date", float(existing["spent"]),
            0.0, 1_000_000_000.0, 2,
        )
        if not accepted:
            return
        self._data["project_budgets"] = [
            r for r in self._data["project_budgets"] if r["project_id"] != project["id"]
        ]
        self._data["project_budgets"].append(
            {
                "project_id": project["id"], "currency": currency.strip() or "EUR",
                "planned": planned, "spent": spent,
            }
        )
        self._save()
        self._refresh_project_details()

    def _refresh_project_details(self) -> None:
        if not hasattr(self, "_stage_table"):
            return
        project = self._selected_project()
        project_id = project["id"] if project else None
        stages = [r for r in self._data["project_stages"] if r["project_id"] == project_id]
        activities = [r for r in self._data["project_activities"] if r["project_id"] == project_id]
        resources = [r for r in self._data["project_resources"] if r["project_id"] == project_id]
        stage_names = {r["id"]: r["title"] for r in stages}
        for table, rows, keys in (
            (self._stage_table, stages, ("title", "status", "notes")),
            (self._activity_table, activities, ("title", "stage_id", "due", "status")),
            (self._resource_table, resources, ("name", "quantity", "unit", "unit_cost")),
        ):
            table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column, key in enumerate(keys):
                    value = stage_names.get(row.get(key), row.get(key, ""))
                    table.setItem(row_index, column, QTableWidgetItem(str(value)))
        budget = next(
            (r for r in self._data["project_budgets"] if r["project_id"] == project_id), None
        )
        self._budget_label.setText(
            (
                f"<b>Budget:</b> {budget['currency']} {budget['planned']:.2f} planned; "
                f"{budget['spent']:.2f} spent; "
                f"{budget['planned'] - budget['spent']:.2f} remaining"
            )
            if budget else "No project budget set."
        )

    def _dossiers_page(self) -> QWidget:
        """Build the dossier workspace around description, context, and composition.

        Dossiers remain independent records. They can be attached to an accessible
        project, can aggregate governed Research records without copying them, and
        can be grouped into a master dossier through explicit parent/child links.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        explanation = QLabel(
            "A dossier is a descriptive case or subject file. It may be independent, "
            "linked to a project, or act as a master dossier containing other dossiers. "
            "Scientific records are linked from Research and remain in their authoritative store."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        actions = QHBoxLayout()
        self._dossier_search = QLineEdit()
        self._dossier_search.setPlaceholderText("Search dossiers…")
        self._dossier_search.textChanged.connect(self._filter_dossiers)
        for label, handler in (
            ("Edit selected", self._edit_dossier),
            ("Duplicate", self._duplicate_dossier),
            ("Defer for review", self._defer_dossier_for_review),
            ("Reassign owner", self._reassign_dossier_owner),
            ("Delete", self._delete_dossier),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
            if label == "Edit selected":
                self._dossier_edit_button = button
            elif label == "Defer for review":
                self._dossier_defer_button = button
            elif label == "Reassign owner":
                self._dossier_reassign_button = button
        actions.insertWidget(0, self._dossier_search, 1)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._dossier_table = QTableWidget(0, 9)
        self._dossier_table.setHorizontalHeaderLabels(
            (
                "Dossier", "Parent dossier", "Type", "Project", "Date", "Sub-dossiers",
                "Scientific links", "Media", "Description",
            )
        )
        self._dossier_table.horizontalHeader().setStretchLastSection(True)
        self._dossier_table.itemSelectionChanged.connect(self._dossier_selected)
        left_layout.addWidget(self._dossier_table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self._dossier_detail_tabs = QTabWidget()
        self._dossier_detail_tabs.addTab(self._dossier_overview_tab(), "Overview")
        self._dossier_detail_tabs.addTab(self._dossier_science_tab(), "Scientific data")
        self._dossier_detail_tabs.addTab(self._dossier_composition_tab(), "Master dossier")
        self._dossier_detail_tabs.addTab(self._dossier_review_tab(), "Review")
        self._dossier_detail_tabs.addTab(self._dossier_context_tab(), "360° context")
        right_layout.addWidget(self._dossier_detail_tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self._pending_dossier_media: tuple[str, ...] = ()
        self._refresh_dossiers()
        return page

    def _dossier_overview_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self._dossier_title = QLineEdit()
        self._dossier_kind = QComboBox()
        self._dossier_kind.addItem("Dossier", "dossier")
        self._dossier_kind.addItem("Master dossier", "master")
        self._dossier_project = QComboBox()
        self._dossier_date = QLineEdit(date.today().isoformat())
        self._dossier_description = QTextEdit()
        self._dossier_description.setMinimumHeight(120)
        self._dossier_notes = QTextEdit()
        self._dossier_notes.setMaximumHeight(90)
        self._dossier_whiteboard = QComboBox()
        self._dossier_media = QLabel("No selected Library media")
        self._dossier_media.setWordWrap(True)
        use_media = QPushButton("Use current Library selection")
        use_media.clicked.connect(self._refresh_dossier_media_selection)
        create = QPushButton("Create Dossier")
        create.clicked.connect(self._create_dossier)
        form.addRow("Title", self._dossier_title)
        form.addRow("Dossier type", self._dossier_kind)
        form.addRow("Project", self._dossier_project)
        form.addRow("Calendar date", self._dossier_date)
        form.addRow("Description", self._dossier_description)
        form.addRow("Notes", self._dossier_notes)
        form.addRow("Attach saved whiteboard", self._dossier_whiteboard)
        form.addRow("Linked media", self._dossier_media)
        form.addRow("", use_media)
        form.addRow(create)
        return tab

    def _dossier_science_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel(
            "Select a dossier. The tabs below show records from its assigned project. "
            "Linking records does not copy or alter the scientific data."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._dossier_science_tabs = QTabWidget()
        self._dossier_science_tables: dict[str, QTableWidget] = {}
        configurations = (
            ("specimen", "Specimens", ("Code", "Taxon", "Status")),
            ("identifier", "Identifiers", ("Specimen", "Type", "Identifier")),
            ("encounter", "Encounters", ("Specimen", "Type", "Date/time")),
            ("survey_event", "Survey events", ("Event", "Status", "Start")),
            ("protocol", "Protocols", ("Protocol", "Method", "Version")),
            ("definition", "Definitions", ("Definition", "Category", "Unit")),
            ("enrichment", "Enrichments", ("Specimen", "Type", "Value")),
            ("sample", "Samples", ("Sample", "Type", "Status")),
            ("laboratory", "Laboratory", ("Sample", "Record", "Status")),
            ("laboratory_media", "Lab media", ("Sample", "Type", "File")),
        )
        for context_type, title, columns in configurations:
            pane = QWidget()
            pane_layout = QVBoxLayout(pane)
            table = QTableWidget(0, len(columns) + 1)
            table.setHorizontalHeaderLabels((*columns, "Linked"))
            table.horizontalHeader().setStretchLastSection(True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            button = QPushButton(f"Link selected {title.lower()}")
            button.clicked.connect(
                lambda _checked=False, kind=context_type: self._link_selected_dossier_context(kind)
            )
            pane_layout.addWidget(table, 1)
            pane_layout.addWidget(button)
            self._dossier_science_tables[context_type] = table
            self._dossier_science_tabs.addTab(pane, title)
        layout.addWidget(self._dossier_science_tabs, 1)
        return tab

    def _dossier_composition_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        hint = QLabel(
            "A master dossier contains references to one or more dossiers. "
            "Child dossiers remain independent and can still be linked to projects."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._dossier_children = QTableWidget(0, 3)
        self._dossier_children.setHorizontalHeaderLabels(("Dossier", "Project", "Description"))
        self._dossier_children.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._dossier_children, 1)
        row = QHBoxLayout()
        add_child = QPushButton("Add dossier to master")
        add_child.clicked.connect(self._add_child_dossier)
        remove_child = QPushButton("Remove selected child")
        remove_child.clicked.connect(self._remove_child_dossier)
        row.addWidget(add_child)
        row.addWidget(remove_child)
        row.addStretch(1)
        layout.addLayout(row)
        return tab

    def _dossier_context_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._dossier_context = QTextEdit()
        self._dossier_context.setReadOnly(True)
        self._dossier_context.setPlaceholderText(
            "Select a dossier to see its description, project, child dossiers, media, "
            "and linked scientific records."
        )
        layout.addWidget(self._dossier_context)
        return tab

    def _dossier_review_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._dossier_review_summary = QLabel("Select a dossier to see its review state.")
        self._dossier_review_summary.setWordWrap(True)
        layout.addWidget(self._dossier_review_summary)
        self._dossier_review_table = QTableWidget(0, 4)
        self._dossier_review_table.setHorizontalHeaderLabels(
            ("Date/time", "User", "Action", "Remark")
        )
        self._dossier_review_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._dossier_review_table, 1)
        self._dossier_review_remark = QTextEdit()
        self._dossier_review_remark.setPlaceholderText(
            "Add a review remark. Reviewers may comment but cannot alter dossier content."
        )
        self._dossier_review_remark.setMaximumHeight(100)
        layout.addWidget(self._dossier_review_remark)
        row = QHBoxLayout()
        self._dossier_add_review_remark = QPushButton("Add review remark")
        self._dossier_add_review_remark.clicked.connect(self._add_dossier_review_remark)
        self._dossier_return_to_observer = QPushButton("Return to observer")
        self._dossier_return_to_observer.clicked.connect(self._return_dossier_to_observer)
        row.addWidget(self._dossier_add_review_remark)
        row.addWidget(self._dossier_return_to_observer)
        row.addStretch(1)
        layout.addLayout(row)
        return tab

    def _actor_id(self) -> str:
        return os.environ.get("FIELDORA_IDENTITY_ID", "local-user")

    @staticmethod
    def _now_text() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _profile_users(self) -> tuple[dict, ...]:
        path = os.environ.get("FIELDORA_PROFILE_STORE")
        if not path:
            return ()
        try:
            return LocalProfileStore(Path(path)).users()
        except (OSError, ValueError, TypeError):
            return ()

    def _is_dossier_administrator(self) -> bool:
        return os.environ.get("FIELDORA_PROFILE_ROLE") == "administrator"

    def _dossier_can_edit(self, dossier: dict | None) -> bool:
        if dossier is None:
            return False
        actor = self._actor_id()
        if self._is_dossier_administrator():
            return True
        if actor != dossier.get("owner_id", dossier.get("created_by")):
            return False
        return dossier.get("review_status", "draft") != "in_review"

    def _dossier_is_reviewer(self, dossier: dict | None) -> bool:
        return bool(dossier and self._actor_id() == dossier.get("reviewer_id"))

    def _audit_dossier(self, dossier: dict, action: str, *, remark: str = "") -> None:
        dossier.setdefault("review_history", []).append(
            {
                "id": str(uuid4()),
                "at": self._now_text(),
                "actor_id": self._actor_id(),
                "action": action,
                "remark": remark.strip(),
            }
        )

    def _notify_dossier_changed(self, dossier: dict | None = None) -> None:
        project_id = str((dossier or {}).get("project_id") or "")
        self._workspace_context.data_changed(project_id, source="dossiers")

    def _accessible_dossier_projects(self) -> tuple[dict, ...]:
        return self._workspace_context.accessible_projects(
            self._project_service, permission="view"
        )

    def _refresh_dossier_project_choices(self) -> None:
        """Reload accessible dossier projects while preserving the selection."""
        if not hasattr(self, "_dossier_project"):
            return
        current_project = self._dossier_project.currentData()
        self._dossier_project.blockSignals(True)
        try:
            self._dossier_project.clear()
            self._dossier_project.addItem("Independent dossier", None)
            for project in self._accessible_dossier_projects():
                self._dossier_project.addItem(project["name"], project["project_id"])
            if current_project:
                index = self._dossier_project.findData(current_project)
                if index >= 0:
                    self._dossier_project.setCurrentIndex(index)
        finally:
            self._dossier_project.blockSignals(False)

    def _workspace_context_event(self, event) -> None:
        if event.source == "dossiers":
            return
        selected_id = (self._selected_dossier() or {}).get("id") if hasattr(self, "_dossier_table") else None
        if event.topic in {"identity.changed", "permissions.changed", "project.changed"}:
            if hasattr(self, "_dossier_project"):
                self._refresh_dossier_project_choices()
            if hasattr(self, "_dossier_table"):
                self._refresh_dossiers(select_id=selected_id)
        if event.topic == "data.changed" and hasattr(self, "_dossier_table"):
            self._refresh_dossiers(select_id=selected_id)

    def _refresh_dossier_media_selection(self) -> None:
        self._pending_dossier_media = tuple(dict.fromkeys(self._selected_asset_ids()))
        count = len(self._pending_dossier_media)
        self._dossier_media.setText(
            f"{count} selected Library item(s) linked"
            if count else "No selected Library media"
        )

    def _create_dossier(self) -> None:
        title = self._dossier_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Dossier title required", "Enter a dossier title.")
            return
        dossier_id = str(uuid4())
        project_id = self._dossier_project.currentData()
        dossier_kind = str(self._dossier_kind.currentData() or "dossier")
        self._data["dossiers"].append(
            {
                "id": dossier_id,
                "title": title,
                "dossier_type": dossier_kind,
                "project_id": project_id,
                "calendar_date": self._dossier_date.text().strip(),
                "description": self._dossier_description.toPlainText().strip(),
                "notes": self._dossier_notes.toPlainText().strip(),
                "created_by": self._actor_id(),
                "owner_id": self._actor_id(),
                "reviewer_id": None,
                "review_status": "draft",
                "review_history": [],
                "created_at": date.today().isoformat(),
                "media_ids": list(self._pending_dossier_media),
            }
        )
        selected_board_id = self._dossier_whiteboard.currentData()
        if selected_board_id:
            self._data["dossier_whiteboards"].append(
                {"dossier_id": dossier_id, "board_id": selected_board_id}
            )
        if self._dossier_date.text().strip():
            self._data["activities"].append(
                {
                    "id": str(uuid4()),
                    "date": self._dossier_date.text().strip(),
                    "title": f"Dossier: {title}",
                }
            )
        self._save()
        self._refresh_dossiers(select_id=dossier_id)
        self._notify_dossier_changed(self._selected_dossier())
        self._dossier_title.clear()
        self._dossier_description.clear()
        self._dossier_notes.clear()
        self._pending_dossier_media = ()
        self._dossier_media.setText("No selected Library media")

    def _selected_dossier(self) -> dict | None:
        row = self._dossier_table.currentRow()
        if row < 0:
            return None
        item = self._dossier_table.item(row, 0)
        dossier_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next(
            (d for d in self._data.get("dossiers", []) if d.get("id") == dossier_id),
            None,
        )

    def _dossier_selected(self) -> None:
        self._refresh_dossier_context()
        self._refresh_dossier_children()
        self._refresh_dossier_science_tabs()
        self._refresh_dossier_review()
        dossier = self._selected_dossier()
        can_edit = self._dossier_can_edit(dossier)
        if hasattr(self, "_dossier_edit_button"):
            self._dossier_edit_button.setEnabled(can_edit)
        if hasattr(self, "_dossier_defer_button"):
            self._dossier_defer_button.setEnabled(
                bool(dossier and can_edit and dossier.get("review_status", "draft") != "in_review")
            )
        if hasattr(self, "_dossier_reassign_button"):
            self._dossier_reassign_button.setEnabled(bool(dossier and self._is_dossier_administrator()))

    def _refresh_dossier_review(self) -> None:
        if not hasattr(self, "_dossier_review_table"):
            return
        dossier = self._selected_dossier()
        if dossier is None:
            self._dossier_review_summary.setText("Select a dossier to see its review state.")
            self._dossier_review_table.setRowCount(0)
            self._dossier_add_review_remark.setEnabled(False)
            self._dossier_return_to_observer.setEnabled(False)
            return
        owner = dossier.get("owner_id", dossier.get("created_by", ""))
        reviewer = dossier.get("reviewer_id") or "Not assigned"
        status = dossier.get("review_status", "draft").replace("_", " ").title()
        self._dossier_review_summary.setText(
            f"<b>Status:</b> {status} &nbsp; <b>Observer/owner:</b> {owner} "
            f"&nbsp; <b>Reviewer:</b> {reviewer}"
        )
        history = dossier.get("review_history", [])
        self._dossier_review_table.setRowCount(len(history))
        for row, entry in enumerate(history):
            values = (
                entry.get("at", ""), entry.get("actor_id", ""),
                entry.get("action", "").replace("_", " ").title(),
                entry.get("remark", ""),
            )
            for column, value in enumerate(values):
                self._dossier_review_table.setItem(row, column, QTableWidgetItem(str(value)))
        reviewer_access = self._dossier_is_reviewer(dossier) or self._is_dossier_administrator()
        in_review = dossier.get("review_status") == "in_review"
        self._dossier_add_review_remark.setEnabled(reviewer_access and in_review)
        self._dossier_return_to_observer.setEnabled(reviewer_access and in_review)
        self._dossier_review_remark.setReadOnly(not (reviewer_access and in_review))

    def _defer_dossier_for_review(self) -> None:
        dossier = self._selected_dossier()
        if not self._dossier_can_edit(dossier):
            return
        users = [u for u in self._profile_users() if u.get("enabled", True) and u.get("username") != self._actor_id()]
        if not users:
            QMessageBox.information(self, "Defer dossier", "No enabled reviewer profiles are available.")
            return
        labels = [f"{u.get('display_name', u['username'])} ({u['username']})" for u in users]
        selected, accepted = QInputDialog.getItem(self, "Defer dossier", "Reviewer", labels, 0, False)
        if not accepted:
            return
        reviewer = users[labels.index(selected)]["username"]
        dossier["owner_id"] = dossier.get("owner_id", dossier.get("created_by", self._actor_id()))
        dossier["reviewer_id"] = reviewer
        dossier["review_status"] = "in_review"
        self._audit_dossier(dossier, "deferred_for_review", remark=f"Assigned to {reviewer}")
        self._save()
        self._refresh_dossiers(select_id=dossier["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)

    def _add_dossier_review_remark(self) -> None:
        dossier = self._selected_dossier()
        if not dossier or dossier.get("review_status") != "in_review":
            return
        if not (self._dossier_is_reviewer(dossier) or self._is_dossier_administrator()):
            return
        remark = self._dossier_review_remark.toPlainText().strip()
        if not remark:
            QMessageBox.information(self, "Review remark", "Enter a remark first.")
            return
        self._audit_dossier(dossier, "review_remark", remark=remark)
        self._dossier_review_remark.clear()
        self._save()
        self._refresh_dossier_review()
        self._notify_dossier_changed(dossier)

    def _return_dossier_to_observer(self) -> None:
        dossier = self._selected_dossier()
        if not dossier or dossier.get("review_status") != "in_review":
            return
        if not (self._dossier_is_reviewer(dossier) or self._is_dossier_administrator()):
            return
        remark = self._dossier_review_remark.toPlainText().strip()
        dossier["review_status"] = "returned"
        self._audit_dossier(dossier, "returned_to_observer", remark=remark)
        self._dossier_review_remark.clear()
        self._save()
        self._refresh_dossiers(select_id=dossier["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)

    def _reassign_dossier_owner(self) -> None:
        dossier = self._selected_dossier()
        if dossier is None or not self._is_dossier_administrator():
            return
        users = [u for u in self._profile_users() if u.get("enabled", True)]
        if not users:
            return
        labels = [f"{u.get('display_name', u['username'])} ({u['username']})" for u in users]
        selected, accepted = QInputDialog.getItem(self, "Reassign dossier", "New observer/owner", labels, 0, False)
        if not accepted:
            return
        previous = dossier.get("owner_id", dossier.get("created_by", ""))
        new_owner = users[labels.index(selected)]["username"]
        dossier["owner_id"] = new_owner
        self._audit_dossier(dossier, "owner_reassigned", remark=f"{previous} → {new_owner}")
        self._save()
        self._refresh_dossiers(select_id=dossier["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)

    def _dossier_records(self, project_id: str) -> dict[str, tuple[dict, ...]]:
        workflows = self._project_service.sample_workflow_records(project_id)
        samples = self._project_service.samples(project_id)
        sample_codes = {str(row.get("sample_id")): str(row.get("sample_code", "")) for row in samples}
        laboratory = tuple(
            {**row, "sample_code": sample_codes.get(str(row.get("sample_id")), "")}
            for row in workflows.get("laboratory_records", [])
        )
        return {
            "specimen": self._project_service.specimens(project_id),
            "identifier": self._project_service.specimen_identifiers(project_id),
            "encounter": self._project_service.specimen_encounters(project_id),
            "survey_event": self._project_service.survey_events(project_id),
            "protocol": self._project_service.survey_protocols(project_id),
            "definition": self._project_service.measurement_definitions(project_id),
            "enrichment": self._project_service.specimen_enrichments(project_id),
            "sample": samples,
            "laboratory": laboratory,
            "laboratory_media": self._project_service.laboratory_media(project_id),
        }

    @staticmethod
    def _dossier_record_id(context_type: str, row: dict) -> str:
        keys = {
            "specimen": "specimen_id", "identifier": "identifier_id",
            "encounter": "encounter_id", "survey_event": "survey_event_id",
            "protocol": "protocol_id", "definition": "definition_id",
            "enrichment": "enrichment_id", "sample": "sample_id",
            "laboratory": "laboratory_id", "laboratory_media": "media_id",
        }
        return str(row.get(keys[context_type], ""))

    @staticmethod
    def _dossier_record_values(context_type: str, row: dict) -> tuple[str, str, str]:
        if context_type == "specimen":
            return str(row.get("specimen_code", "")), str(row.get("taxon_name", "")), str(row.get("status_code", ""))
        if context_type == "identifier":
            return str(row.get("specimen_code", "")), str(row.get("identifier_type", "")), str(row.get("identifier_value", ""))
        if context_type == "encounter":
            return str(row.get("specimen_code", "")), str(row.get("encounter_type", "")), str(row.get("occurred_at", ""))
        if context_type == "survey_event":
            return str(row.get("name", "")), str(row.get("status", "")), str(row.get("start_text", ""))
        if context_type == "protocol":
            return str(row.get("name", "")), str(row.get("method", "")), str(row.get("version", ""))
        if context_type == "definition":
            return str(row.get("name", "")), str(row.get("category", "")), str(row.get("unit", ""))
        if context_type == "enrichment":
            return str(row.get("specimen_code", "")), str(row.get("enrichment_type", "")), f"{row.get('value_text', '')} {row.get('unit', '')}".strip()
        if context_type == "sample":
            return str(row.get("sample_code", "")), str(row.get("sample_type", "")), str(row.get("status", ""))
        if context_type == "laboratory":
            return str(row.get("sample_code", "")), str(row.get("record_type", "")), str(row.get("status", ""))
        return str(row.get("sample_code", "")), str(row.get("media_type", "")), str(row.get("file_name", ""))

    def _refresh_dossier_science_tabs(self) -> None:
        if not hasattr(self, "_dossier_science_tables"):
            return
        dossier = self._selected_dossier()
        links = self._project_service.dossier_context(dossier["id"]) if dossier else ()
        linked = {(x["context_type"], x["context_id"]) for x in links}
        project_id = dossier.get("project_id") if dossier else None
        records = self._dossier_records(str(project_id)) if project_id else {}
        for context_type, table in self._dossier_science_tables.items():
            rows = records.get(context_type, ())
            table.setRowCount(len(rows))
            for row_index, record in enumerate(rows):
                record_id = self._dossier_record_id(context_type, record)
                values = (*self._dossier_record_values(context_type, record), "Yes" if (context_type, record_id) in linked else "")
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, record_id)
                    table.setItem(row_index, column, item)

    def _link_selected_dossier_context(self, context_type: str) -> None:
        dossier = self._selected_dossier()
        if dossier is None:
            QMessageBox.information(self, "Link scientific data", "Select a dossier first.")
            return
        project_id = dossier.get("project_id")
        if not project_id:
            QMessageBox.information(self, "Link scientific data", "Assign the dossier to a project first.")
            return
        table = self._dossier_science_tables[context_type]
        row = table.currentRow()
        item = table.item(row, 0) if row >= 0 else None
        context_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not context_id:
            QMessageBox.information(self, "Link scientific data", "Select a record first.")
            return
        try:
            self._project_service.link_dossier_context(
                dossier["id"], str(project_id), context_type, str(context_id),
                actor_id=self._actor_id(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Link scientific data", str(exc))
            return
        self._refresh_dossier_science_tabs()
        self._refresh_dossier_context()
        self._refresh_dossiers(select_id=dossier["id"])

    def _refresh_dossier_children(self) -> None:
        if not hasattr(self, "_dossier_children"):
            return
        dossier = self._selected_dossier()
        links = self._data.get("dossier_links", [])
        child_ids = [x["child_dossier_id"] for x in links if dossier and x["parent_dossier_id"] == dossier["id"]]
        dossiers = {x["id"]: x for x in self._data.get("dossiers", [])}
        projects = {x["project_id"]: x["name"] for x in self._accessible_dossier_projects()}
        children = [dossiers[x] for x in child_ids if x in dossiers]
        self._dossier_children.setRowCount(len(children))
        for row, child in enumerate(children):
            values = (child["title"], projects.get(child.get("project_id"), "Independent"), child.get("description", child.get("notes", "")))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, child["id"])
                self._dossier_children.setItem(row, column, item)

    def _add_child_dossier(self) -> None:
        parent = self._selected_dossier()
        if parent is None:
            QMessageBox.information(self, "Master dossier", "Select a master dossier first.")
            return
        if parent.get("dossier_type", "dossier") != "master":
            QMessageBox.information(self, "Master dossier", "Change this dossier to type Master dossier first.")
            return
        existing = {x["child_dossier_id"] for x in self._data.get("dossier_links", []) if x["parent_dossier_id"] == parent["id"]}
        candidates = [x for x in self._data.get("dossiers", []) if x["id"] != parent["id"] and x["id"] not in existing]
        if not candidates:
            QMessageBox.information(self, "Master dossier", "No other dossiers are available.")
            return
        labels = [x["title"] for x in candidates]
        selected, accepted = QInputDialog.getItem(self, "Add dossier", "Dossier", labels, 0, False)
        if not accepted:
            return
        child = candidates[labels.index(selected)]
        self._data.setdefault("dossier_links", []).append(
            {"id": str(uuid4()), "parent_dossier_id": parent["id"], "child_dossier_id": child["id"], "relationship": "contains"}
        )
        self._save()
        self._refresh_dossier_children()
        self._refresh_dossiers(select_id=parent["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)
        self._refresh_dossier_context()

    def _remove_child_dossier(self) -> None:
        parent = self._selected_dossier()
        row = self._dossier_children.currentRow() if hasattr(self, "_dossier_children") else -1
        item = self._dossier_children.item(row, 0) if row >= 0 else None
        child_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if parent is None or not child_id:
            return
        self._data["dossier_links"] = [
            x for x in self._data.get("dossier_links", [])
            if not (x["parent_dossier_id"] == parent["id"] and x["child_dossier_id"] == child_id)
        ]
        self._save()
        self._refresh_dossier_children()
        self._refresh_dossiers(select_id=parent["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)
        self._refresh_dossier_context()

    def _refresh_dossier_context(self) -> None:
        if not hasattr(self, "_dossier_context"):
            return
        dossier = self._selected_dossier()
        if dossier is None:
            self._dossier_context.clear()
            return
        projects = {x["project_id"]: x for x in self._accessible_dossier_projects()}
        project = projects.get(dossier.get("project_id"))
        links = self._project_service.dossier_context(dossier["id"])
        child_links = [x for x in self._data.get("dossier_links", []) if x["parent_dossier_id"] == dossier["id"]]
        dossier_by_id = {x["id"]: x for x in self._data.get("dossiers", [])}
        sections = [f"<h2>{dossier['title']}</h2>"]
        sections.append(f"<p><b>Type:</b> {dossier.get('dossier_type', 'dossier').replace('_', ' ').title()}</p>")
        sections.append(f"<p><b>Project:</b> {project['name'] if project else 'Independent'}</p>")
        sections.append(
            f"<p><b>Observer/owner:</b> {dossier.get('owner_id', dossier.get('created_by', ''))}</p>"
        )
        sections.append(
            f"<p><b>Review status:</b> {dossier.get('review_status', 'draft').replace('_', ' ').title()}"
            f" &nbsp; <b>Reviewer:</b> {dossier.get('reviewer_id') or 'Not assigned'}</p>"
        )
        description = dossier.get("description") or dossier.get("notes", "")
        if description:
            sections.append(f"<h3>Description</h3><p>{description}</p>")
        if child_links:
            sections.append("<h3>Contained dossiers</h3><ul>" + "".join(
                f"<li>{dossier_by_id[x['child_dossier_id']]['title']}</li>"
                for x in child_links if x["child_dossier_id"] in dossier_by_id
            ) + "</ul>")
        if links:
            counts: dict[str, int] = {}
            for link in links:
                counts[link["context_type"]] = counts.get(link["context_type"], 0) + 1
            sections.append("<h3>Scientific links</h3><ul>" + "".join(
                f"<li>{kind.replace('_', ' ').title()}: {count}</li>" for kind, count in sorted(counts.items())
            ) + "</ul>")
        else:
            sections.append("<p>No structured scientific records linked yet.</p>")
        sections.append(f"<p><b>Library media:</b> {len(dossier.get('media_ids', []))}</p>")
        self._dossier_context.setHtml("".join(sections))

    def _edit_dossier(self) -> None:
        dossier = self._selected_dossier()
        if dossier is None or not self._dossier_can_edit(dossier):
            if dossier is not None:
                QMessageBox.information(
                    self,
                    "Dossier is read-only",
                    "Only the dossier owner or a dossier administrator may alter it. "
                    "A dossier under review remains read-only until the reviewer returns it.",
                )
            return
        title, accepted = QInputDialog.getText(self, "Edit dossier", "Title", text=dossier["title"])
        if not accepted or not title.strip():
            return
        description, accepted = QInputDialog.getMultiLineText(
            self, "Edit dossier", "Description", dossier.get("description", dossier.get("notes", ""))
        )
        if not accepted:
            return
        type_labels = ["Dossier", "Master dossier"]
        current = 1 if dossier.get("dossier_type") == "master" else 0
        selected_type, accepted = QInputDialog.getItem(self, "Edit dossier", "Type", type_labels, current, False)
        if not accepted:
            return
        projects = self._accessible_dossier_projects()
        project_labels = ["Independent dossier", *[x["name"] for x in projects]]
        current_project = 0
        for index, project in enumerate(projects, start=1):
            if project["project_id"] == dossier.get("project_id"):
                current_project = index
                break
        selected_project, accepted = QInputDialog.getItem(self, "Edit dossier", "Project", project_labels, current_project, False)
        if not accepted:
            return
        dossier["title"] = title.strip()
        dossier["description"] = description.strip()
        dossier["dossier_type"] = "master" if selected_type == "Master dossier" else "dossier"
        dossier["project_id"] = None if selected_project == "Independent dossier" else projects[project_labels.index(selected_project) - 1]["project_id"]
        self._audit_dossier(dossier, "dossier_edited")
        self._save()
        self._refresh_dossiers(select_id=dossier["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)

    def _duplicate_dossier(self) -> None:
        dossier = self._selected_dossier()
        if dossier is None:
            return
        duplicate = {
            **dossier,
            "id": str(uuid4()),
            "title": f"{dossier['title']} (copy)",
            "dossier_type": "dossier",
            "created_by": self._actor_id(),
            "owner_id": self._actor_id(),
            "reviewer_id": None,
            "review_status": "draft",
            "review_history": [],
            "created_at": date.today().isoformat(),
            "media_ids": list(dossier.get("media_ids", [])),
        }
        self._data["dossiers"].append(duplicate)
        for link in tuple(self._data["dossier_whiteboards"]):
            if link["dossier_id"] == dossier["id"]:
                self._data["dossier_whiteboards"].append({"dossier_id": duplicate["id"], "board_id": link["board_id"]})
        self._save()
        self._refresh_dossiers(select_id=duplicate["id"])
        self._notify_dossier_changed(dossier if "dossier" in locals() else parent if "parent" in locals() else duplicate)

    def _delete_dossier(self) -> None:
        dossier = self._selected_dossier()
        if dossier is None:
            return
        if not (self._dossier_can_edit(dossier) or self._is_dossier_administrator()):
            QMessageBox.information(self, "Dossier is read-only", "You are not allowed to delete this dossier.")
            return
        if QMessageBox.question(
            self, "Delete dossier",
            f"Delete ‘{dossier['title']}’ and its links? Scientific records, Library assets, and whiteboards will not be deleted.",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._data["dossiers"].remove(dossier)
        self._data["dossier_whiteboards"] = [x for x in self._data["dossier_whiteboards"] if x["dossier_id"] != dossier["id"]]
        self._data["dossier_links"] = [x for x in self._data.get("dossier_links", []) if dossier["id"] not in (x["parent_dossier_id"], x["child_dossier_id"])]
        self._save()
        self._refresh_dossiers()

    def _filter_dossiers(self, query: str) -> None:
        needle = query.strip().casefold()
        for row in range(self._dossier_table.rowCount()):
            text = " ".join(
                self._dossier_table.item(row, column).text()
                for column in range(self._dossier_table.columnCount())
                if self._dossier_table.item(row, column) is not None
            ).casefold()
            self._dossier_table.setRowHidden(row, bool(needle) and needle not in text)

    def _refresh_dossiers(self, *, select_id: str | None = None) -> None:
        if not hasattr(self, "_dossier_table"):
            return
        accessible_projects = self._accessible_dossier_projects()
        projects = {row["project_id"]: row["name"] for row in accessible_projects}
        current_board = self._dossier_whiteboard.currentData()
        self._refresh_dossier_project_choices()
        self._dossier_whiteboard.clear()
        self._dossier_whiteboard.addItem("No whiteboard", None)
        for board in self._data["whiteboards"]:
            self._dossier_whiteboard.addItem(board["title"], board["id"])
        if current_board:
            index = self._dossier_whiteboard.findData(current_board)
            if index >= 0:
                self._dossier_whiteboard.setCurrentIndex(index)
        dossiers = self._data.get("dossiers", [])
        links = self._data.get("dossier_links", [])
        by_id = {dossier["id"]: dossier for dossier in dossiers}
        parent_by_child = {link["child_dossier_id"]: link["parent_dossier_id"] for link in links}
        children_by_parent: dict[str, list[dict]] = {}
        for link in links:
            child = by_id.get(link["child_dossier_id"])
            if child is not None:
                children_by_parent.setdefault(link["parent_dossier_id"], []).append(child)
        ordered: list[tuple[dict, int]] = []
        visited: set[str] = set()
        def append_branch(dossier: dict, depth: int) -> None:
            dossier_id = dossier["id"]
            if dossier_id in visited:
                return
            visited.add(dossier_id)
            ordered.append((dossier, depth))
            for child in sorted(children_by_parent.get(dossier_id, []), key=lambda item: item.get("title", "").casefold()):
                append_branch(child, depth + 1)
        roots = [dossier for dossier in dossiers if dossier["id"] not in parent_by_child]
        for dossier in sorted(roots, key=lambda item: item.get("title", "").casefold()):
            append_branch(dossier, 0)
        for dossier in sorted(dossiers, key=lambda item: item.get("title", "").casefold()):
            append_branch(dossier, 0)
        context_counts: dict[str, int] = {}
        for dossier in dossiers:
            context_counts[dossier["id"]] = len(self._project_service.dossier_context(dossier["id"]))
        self._dossier_table.setRowCount(len(ordered))
        selected_row = -1
        for row_index, (dossier, depth) in enumerate(ordered):
            child_count = sum(1 for x in links if x["parent_dossier_id"] == dossier["id"])
            parent = by_id.get(parent_by_child.get(dossier["id"], ""))
            values = (
                f"{'    ' * depth}{'↳ ' if depth else ''}{dossier['title']}",
                parent.get("title", "") if parent else "",
                "Master dossier" if dossier.get("dossier_type") == "master" else "Dossier",
                projects.get(dossier.get("project_id"), "Independent"),
                dossier.get("calendar_date", ""),
                child_count,
                context_counts.get(dossier["id"], 0),
                len(dossier.get("media_ids", [])),
                dossier.get("description", dossier.get("notes", "")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, dossier["id"])
                self._dossier_table.setItem(row_index, column, item)
            if dossier["id"] == select_id:
                selected_row = row_index
        if selected_row >= 0:
            self._dossier_table.selectRow(selected_row)
        self._filter_dossiers(self._dossier_search.text())
        self._dossier_selected()

    def _whiteboard_page(self) -> QWidget:
        page = QWidget()
        description = QLabel(
            "<h3>Offline Excalidraw whiteboards</h3>"
            "<p>Whiteboards are standard <code>.excalidraw</code> documents stored under "
            "<b>Documents/Whiteboards</b>. The complete Excalidraw editor is bundled inside "
            "Fieldora and makes no network requests. Fieldora keeps document snapshots here; the former Science "
            "whiteboard database is not imported or changed.</p>"
        )
        description.setWordWrap(True)
        self._excalidraw_list = QListWidget()
        self._excalidraw_list.itemDoubleClicked.connect(lambda _item: self._open_excalidraw())
        self._excalidraw_editor = EmbeddedExcalidrawEditor(self._excalidraw, page)
        self._excalidraw_editor.document_saved.connect(self._refresh_excalidraw)
        new_board = QPushButton("New Excalidraw document…")
        new_board.clicked.connect(self._new_excalidraw)
        import_board = QPushButton("Import .excalidraw…")
        import_board.clicked.connect(self._import_excalidraw)
        open_board = QPushButton("Open in Fieldora")
        open_board.clicked.connect(self._open_excalidraw)
        snapshot = QPushButton("Create document version")
        snapshot.clicked.connect(self._snapshot_excalidraw)
        reveal = QPushButton("Open Whiteboards folder")
        reveal.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._excalidraw.root)))
        )
        buttons = QHBoxLayout()
        buttons.addWidget(new_board)
        buttons.addWidget(import_board)
        buttons.addWidget(open_board)
        buttons.addWidget(snapshot)
        buttons.addWidget(reveal)
        buttons.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(description)
        layout.addLayout(buttons)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._excalidraw_list)
        splitter.addWidget(self._excalidraw_editor)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1000])
        layout.addWidget(splitter, 1)
        try:
            initial_document = self._excalidraw.ensure_default_document()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot initialize Excalidraw", str(exc))
            self._refresh_excalidraw()
        else:
            self._refresh_excalidraw()
            self._select_excalidraw(initial_document)
            self._excalidraw_editor.open_document(initial_document)
        return page

    def _refresh_excalidraw(self) -> None:
        if not hasattr(self, "_excalidraw_list"):
            return
        self._excalidraw_list.clear()
        for document in self._excalidraw.list_documents():
            item = QListWidgetItem(
                f"{document.title} — {document.revision_count} version(s) — "
                f"{document.modified_at_utc}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(document.path))
            self._excalidraw_list.addItem(item)

    def _selected_excalidraw(self) -> Path | None:
        item = self._excalidraw_list.currentItem()
        return Path(str(item.data(Qt.ItemDataRole.UserRole))) if item is not None else None

    def _new_excalidraw(self) -> None:
        title, accepted = QInputDialog.getText(
            self, "New Excalidraw document", "Document title"
        )
        if not accepted:
            return
        try:
            path = self._excalidraw.create(title)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot create whiteboard", str(exc))
            return
        self._refresh_excalidraw()
        self._select_excalidraw(path)
        self._excalidraw_editor.open_document(path)

    def _import_excalidraw(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Import Excalidraw document", "", "Excalidraw (*.excalidraw)"
        )
        if not path:
            return
        try:
            self._excalidraw.import_document(Path(path))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot import whiteboard", str(exc))
            return
        self._refresh_excalidraw()

    def _open_excalidraw(self) -> None:
        path = self._selected_excalidraw()
        if path is None:
            return
        self._excalidraw_editor.open_document(path)

    def _select_excalidraw(self, path: Path) -> None:
        for index in range(self._excalidraw_list.count()):
            item = self._excalidraw_list.item(index)
            if Path(str(item.data(Qt.ItemDataRole.UserRole))) == path:
                self._excalidraw_list.setCurrentItem(item)
                return

    def _snapshot_excalidraw(self) -> None:
        path = self._selected_excalidraw()
        if path is None:
            return
        try:
            self._excalidraw.snapshot(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot create document version", str(exc))
            return
        self._refresh_excalidraw()

    def _refresh_board_picker(self) -> None:
        if not hasattr(self, "_board_picker"):
            return
        current = self._board_picker.currentData()
        self._board_picker.blockSignals(True)
        self._board_picker.clear()
        for board in self._data["whiteboards"]:
            self._board_picker.addItem(board["title"], board["id"])
        if current:
            index = self._board_picker.findData(current)
            if index >= 0:
                self._board_picker.setCurrentIndex(index)
        self._board_picker.blockSignals(False)

    def _current_board_id(self) -> str | None:
        if not hasattr(self, "_board_picker"):
            return None
        value = self._board_picker.currentData()
        return str(value) if value else None

    def _new_whiteboard(self) -> None:
        title, accepted = QInputDialog.getText(self, "New whiteboard", "Board title")
        if not accepted or not title.strip():
            return
        board_id = str(uuid4())
        today = date.today().isoformat()
        self._data["whiteboards"].append(
            {
                "id": board_id, "title": title.strip(),
                "created_at": today, "updated_at": today,
            }
        )
        self._save()
        self._refresh_board_picker()
        index = self._board_picker.findData(board_id)
        if index >= 0:
            self._board_picker.setCurrentIndex(index)
        self._refresh_dossiers()

    def _save_whiteboard(self) -> None:
        board_id = self._current_board_id()
        board = next(
            (row for row in self._data["whiteboards"] if row["id"] == board_id), None
        )
        if board is None:
            return
        title, accepted = QInputDialog.getText(
            self, "Save whiteboard", "Board title", text=board["title"]
        )
        if not accepted or not title.strip():
            return
        board["title"] = title.strip()
        board["updated_at"] = date.today().isoformat()
        self._save()
        self._refresh_board_picker()
        self._refresh_dossiers()

    def _add_library_references(self) -> None:
        board_id = self._current_board_id()
        asset_ids = tuple(dict.fromkeys(self._selected_asset_ids()))
        if board_id is None or not asset_ids:
            QMessageBox.information(
                self, "Library selection required",
                "Select one or more photos, videos, sounds, or documents in the "
                "Library and return to this whiteboard.",
            )
            return
        media_kind, accepted = QInputDialog.getItem(
            self, "Library reference", "Selected item type",
            ("Image", "Video", "Sound", "Document", "Mixed selection"), 0, False,
        )
        if not accepted:
            return
        start = len(self._board_elements())
        for index, asset_id in enumerate(asset_ids):
            self._data["whiteboard_elements"].append(
                {
                    "id": str(uuid4()), "board_id": board_id, "kind": "library_ref",
                    "asset_id": asset_id, "media_kind": media_kind,
                    "title": f"{media_kind}: {asset_id}", "x": 40 + (index % 4) * 190,
                    "y": 40 + ((start + index) // 4) * 100,
                    "color": "#1565c0", "order": start + index,
                }
            )
        self._save()
        self._refresh_board()

    def _add_icon(self, name: str) -> None:
        board_id = self._current_board_id()
        if board_id is None:
            return
        index = len(self._board_elements())
        self._data["whiteboard_elements"].append(
            {
                "id": str(uuid4()), "board_id": board_id, "kind": "icon",
                "name": name, "x": 40 + (index % 5) * 145,
                "y": 40 + (index // 5) * 90, "color": "#455a64", "order": index,
            }
        )
        self._save()
        self._refresh_board()

    def _import_svg_icon(self) -> None:
        board_id = self._current_board_id()
        if board_id is None:
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import icon from an SVG pack", "", "SVG files (*.svg)"
        )
        if not path:
            return
        try:
            svg = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot import icon", str(exc))
            return
        lowered = svg.lower()
        unsafe = any(
            marker in lowered
            for marker in ("<script", "javascript:", 'href="http', "href='http", "file:")
        )
        if (
            "<svg" not in lowered[:1000]
            or len(svg.encode("utf-8")) > 1_000_000
            or unsafe
        ):
            QMessageBox.warning(
                self, "Invalid SVG icon",
                "Choose a self-contained SVG icon smaller than 1 MB, without scripts "
                "or external links. Verify that its license permits use.",
            )
            return
        index = len(self._board_elements())
        self._data["whiteboard_elements"].append(
            {
                "id": str(uuid4()), "board_id": board_id, "kind": "svg_icon",
                "name": Path(path).stem, "svg": svg,
                "x": 40 + (index % 5) * 145, "y": 40 + (index // 5) * 90,
                "color": "#455a64", "order": index,
            }
        )
        self._save()
        self._refresh_board()

    def _board_elements(self) -> list[dict]:
        board_id = self._current_board_id()
        return [
            row for row in self._data["whiteboard_elements"]
            if row["board_id"] == board_id
        ]

    def _persist_board_positions(self) -> None:
        changed = False
        elements = {row["id"]: row for row in self._board_elements()}
        for item in self._board_scene.items():
            element_id = item.data(0)
            element = elements.get(str(element_id)) if element_id else None
            if element is None:
                continue
            origin = item.scenePos()
            if hasattr(item, "rect"):
                rectangle = item.rect()
                x = float(origin.x() + rectangle.x())
                y = float(origin.y() + rectangle.y())
            else:
                x, y = float(origin.x()), float(origin.y())
            if element.get("x") != x or element.get("y") != y:
                element["x"], element["y"] = x, y
                changed = True
        if changed:
            self._save()

    def _export_whiteboard_svg(self) -> None:
        board_id = self._current_board_id()
        if board_id is None:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export whiteboard as SVG", "whiteboard.svg", "SVG files (*.svg)"
        )
        if not path:
            return
        generator = QSvgGenerator()
        generator.setFileName(path)
        bounds = self._board_scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        generator.setViewBox(bounds.toRect())
        generator.setTitle(self._board_picker.currentText())
        painter = QPainter(generator)
        self._board_scene.render(painter)
        painter.end()

    def _export_whiteboard_pdf(self) -> None:
        board_id = self._current_board_id()
        if board_id is None:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export whiteboard as PDF", "whiteboard.pdf", "PDF files (*.pdf)"
        )
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        painter = QPainter(printer)
        self._board_scene.render(painter)
        painter.end()

    def _add_shape(self, shape: dict) -> None:
        board_id = self._current_board_id()
        if board_id is None:
            return
        shape["board_id"] = board_id
        shape["order"] = len(self._board_elements())
        self._data["whiteboard_elements"].append(shape)
        self._save()
        self._refresh_board()

    def _undo_board(self) -> None:
        elements = self._board_elements()
        if not elements:
            return
        self._data["whiteboard_elements"].remove(elements[-1])
        self._save()
        self._refresh_board()

    def _artifact_page(self, category: str) -> QWidget:
        page = QWidget()
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        fields: dict[str, QLineEdit | QTextEdit] = {}
        labels = (
            ("scientific_name", "Scientific name"),
            ("common_name", "Common name"),
            ("observed_on", "Observed/collected date"),
            ("location", "Location"),
            ("length_mm", "Length (mm)"),
            ("width_mm", "Width (mm)"),
            ("height_mm", "Height (mm)"),
            ("weight_g", "Weight (g)"),
            ("primary_color", "Primary color"),
            ("secondary_color", "Secondary color"),
            ("sex_or_stage", "Sex / life stage"),
            ("quantity", "Quantity"),
        )
        if category == "plant":
            labels += (("flower_diameter_mm", "Flower diameter (mm)"),)
        for key, label in labels:
            field = QLineEdit()
            if key == "observed_on":
                field.setText(date.today().isoformat())
            fields[key] = field
            form.addRow(label, field)
        notes = QTextEdit()
        notes.setMaximumHeight(90)
        fields["notes"] = notes
        form.addRow("Notes / method", notes)
        register = QPushButton("Register Artifact")
        register.clicked.connect(
            lambda _checked=False, kind=category, controls=fields: self._register_artifact(
                kind, controls
            )
        )
        form.addRow(register)
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(
            (
                "Scientific name", "Common name", "Date", "Size (L×W×H mm)",
                "Weight g", "Color", "Location",
            )
        )
        table.horizontalHeader().setStretchLastSection(True)
        self._artifact_tables = getattr(self, "_artifact_tables", {})
        self._artifact_tables[category] = table
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(form_widget)
        splitter.addWidget(table)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(page)
        heading = {
            "animal": "Animal specimen and observation artifacts",
            "plant": "Plant and flower specimen artifacts",
            "other": "Fungi, minerals, samples, traces, and other science artifacts",
        }[category]
        description = QLabel(f"<b>{heading}</b>")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addWidget(splitter, 1)
        return page

    @staticmethod
    def _optional_number(text: str, label: str) -> float | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number") from exc
        if value < 0:
            raise ValueError(f"{label} cannot be negative")
        return value

    def _register_artifact(
        self, category: str, fields: dict[str, QLineEdit | QTextEdit]
    ) -> None:
        def text(key: str) -> str:
            widget = fields.get(key)
            if isinstance(widget, QTextEdit):
                return widget.toPlainText().strip()
            return widget.text().strip() if isinstance(widget, QLineEdit) else ""

        if not text("scientific_name") and not text("common_name"):
            QMessageBox.warning(
                self, "Artifact identity required",
                "Enter at least a scientific name or common name."
            )
            return
        try:
            quantity_value = self._optional_number(text("quantity"), "Quantity")
            artifact = {
                "id": str(uuid4()),
                "category": category,
                "scientific_name": text("scientific_name"),
                "common_name": text("common_name"),
                "observed_on": text("observed_on"),
                "location": text("location"),
                "length_mm": self._optional_number(text("length_mm"), "Length"),
                "width_mm": self._optional_number(text("width_mm"), "Width"),
                "height_mm": self._optional_number(text("height_mm"), "Height"),
                "weight_g": self._optional_number(text("weight_g"), "Weight"),
                "primary_color": text("primary_color"),
                "secondary_color": text("secondary_color"),
                "sex_or_stage": text("sex_or_stage"),
                "quantity": int(quantity_value) if quantity_value is not None else None,
                "flower_diameter_mm": self._optional_number(
                    text("flower_diameter_mm"), "Flower diameter"
                ),
                "notes": text("notes"),
                "created_at": date.today().isoformat(),
            }
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid measurement", str(exc))
            return
        self._data["artifacts"].append(artifact)
        self._save()
        self._refresh_artifacts()
        for key, widget in fields.items():
            if key == "observed_on":
                continue
            if isinstance(widget, QTextEdit):
                widget.clear()
            else:
                widget.clear()

    def _refresh_artifacts(self) -> None:
        if not hasattr(self, "_artifact_tables"):
            return
        for category, table in self._artifact_tables.items():
            rows = [
                row for row in self._data.get("artifacts", [])
                if row.get("category") == category
            ]
            table.setRowCount(len(rows))
            for row_index, artifact in enumerate(rows):
                size = " × ".join(
                    "" if artifact.get(key) is None else str(artifact[key])
                    for key in ("length_mm", "width_mm", "height_mm")
                ).strip(" ×")
                color = " / ".join(
                    value for value in (
                        str(artifact.get("primary_color") or ""),
                        str(artifact.get("secondary_color") or ""),
                    ) if value
                )
                values = (
                    artifact.get("scientific_name"), artifact.get("common_name"),
                    artifact.get("observed_on"), size, artifact.get("weight_g"),
                    color, artifact.get("location"),
                )
                for column, value in enumerate(values):
                    table.setItem(
                        row_index, column,
                        QTableWidgetItem("" if value is None else str(value)),
                    )

    def _add_note(self) -> None:
        text, accepted = QInputDialog.getMultiLineText(
            self, "Whiteboard note", "Idea, question, method, or finding"
        )
        if not accepted or not text.strip():
            return
        board_id = self._current_board_id()
        if board_id is None:
            return
        index = len(self._board_elements())
        self._data["whiteboard_elements"].append(
            {
                "id": str(uuid4()), "board_id": board_id, "kind": "sticky",
                "text": text.strip(), "color": "#776b2e", "order": index,
                "x": 30 + (index % 4) * 190,
                "y": 30 + (index // 4) * 130,
            }
        )
        self._save()
        self._refresh_board()

    def _clear_board(self) -> None:
        if QMessageBox.question(
            self, "Clear whiteboard", "Remove all drawings and sticky notes?"
        ) != QMessageBox.StandardButton.Yes:
            return
        board_id = self._current_board_id()
        self._data["whiteboard_elements"] = [
            row for row in self._data["whiteboard_elements"]
            if row["board_id"] != board_id
        ]
        self._save()
        self._refresh_board()

    def _refresh_board(self) -> None:
        if not hasattr(self, "_board_scene"):
            return
        self._board_scene.clear()
        for element in self._board_elements():
            pen = QPen(QColor(str(element.get("color", "#263238"))), 2.0)
            kind = element.get("kind")
            if kind == "svg_icon":
                item = QGraphicsSvgItem()
                svg_renderer = QSvgRenderer(
                    QByteArray(str(element.get("svg", "")).encode("utf-8")), item
                )
                item.setSharedRenderer(svg_renderer)
                bounds = svg_renderer.defaultSize()
                largest = max(bounds.width(), bounds.height(), 1)
                item.setScale(72.0 / largest)
                item.setPos(float(element.get("x", 0)), float(element.get("y", 0)))
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                item.setData(0, element["id"])
                self._board_scene.addItem(item)
                continue
            if kind == "pen":
                points = element.get("points", [])
                if points:
                    path = QPainterPath()
                    path.moveTo(float(points[0][0]), float(points[0][1]))
                    for point in points[1:]:
                        path.lineTo(float(point[0]), float(point[1]))
                    self._board_scene.addPath(path, pen)
                continue
            if kind in {"sticky", "library_ref", "icon"}:
                x, y = float(element.get("x", 0)), float(element.get("y", 0))
                if kind == "sticky":
                    width, height = 170, 105
                    fill, outline = QColor("#fff1a8"), QColor("#776b2e")
                    label = str(element.get("text", ""))
                elif kind == "library_ref":
                    width, height = 180, 78
                    fill, outline = QColor("#e3f2fd"), QColor("#1565c0")
                    label = (
                        f"{element.get('media_kind', 'Library item')}\n"
                        f"{element.get('asset_id', '')}"
                    )
                else:
                    width, height = 125, 62
                    fill, outline = QColor("#eceff1"), QColor("#455a64")
                    label = str(element.get("name", "Icon"))
                rectangle = self._board_scene.addRect(
                    x, y, width, height, QPen(outline), fill
                )
                rectangle.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True
                )
                rectangle.setData(0, element["id"])
                text = self._board_scene.addText(label)
                text.setTextWidth(width - 20)
                text.setDefaultTextColor(QColor("#202124"))
                text.setPos(x + 10, y + 8)
                text.setParentItem(rectangle)
                continue
            x1, y1 = float(element.get("x1", 0)), float(element.get("y1", 0))
            x2, y2 = float(element.get("x2", 0)), float(element.get("y2", 0))
            if kind == "line":
                self._board_scene.addLine(x1, y1, x2, y2, pen)
            elif kind == "rectangle":
                self._board_scene.addRect(
                    min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1), pen
                )
            elif kind == "ellipse":
                self._board_scene.addEllipse(
                    min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1), pen
                )
        self._board_scene.setSceneRect(
            self._board_scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        )

    def _calendar_page(self) -> QWidget:
        page = QWidget()
        self._calendar = ActivityCountCalendar()
        self._calendar.selectionChanged.connect(self._refresh_calendar)
        self._activities = QListWidget()
        self._activities.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        add = QPushButton("Add Activity")
        add.clicked.connect(self._add_activity)
        remove = QPushButton("Remove Activity")
        remove.clicked.connect(self._remove_activity)
        export = QPushButton("Export calendar (.ics)")
        export.clicked.connect(self._export_calendar)
        google = QPushButton("Add selected to Google Calendar")
        google.clicked.connect(lambda: self._open_calendar_provider("google"))
        outlook = QPushButton("Add selected to Outlook")
        outlook.clicked.connect(lambda: self._open_calendar_provider("outlook"))
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("<b>Activities on selected date</b>"))
        side_layout.addWidget(self._activities)
        side_layout.addWidget(add)
        side_layout.addWidget(remove)
        side_layout.addWidget(export)
        side_layout.addWidget(google)
        side_layout.addWidget(outlook)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._calendar)
        splitter.addWidget(side)
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def _selected_date(self) -> str:
        selected: QDate = self._calendar.selectedDate()
        return selected.toString(Qt.DateFormat.ISODate)

    def _add_activity(self) -> None:
        title, accepted = QInputDialog.getText(
            self, "New science activity", "Activity"
        )
        if not accepted or not title.strip():
            return
        self._data["activities"].append(
            {"id": str(uuid4()), "date": self._selected_date(), "title": title.strip()}
        )
        self._save()
        self._refresh_calendar()

    def _remove_activity(self) -> None:
        item = self._activities.currentItem()
        if item is None:
            return
        activity_id = item.data(Qt.ItemDataRole.UserRole)
        self._data["activities"] = [
            activity for activity in self._data["activities"]
            if activity.get("id") != activity_id
        ]
        self._save()
        self._refresh_calendar()

    def _calendar_events(self) -> tuple[CalendarEvent, ...]:
        events = [
            CalendarEvent(
                event_id=str(activity.get("id", "")),
                title=str(activity.get("title", "")),
                event_date=str(activity.get("date", "")),
                description="Fieldora research activity",
            )
            for activity in self._data.get("activities", [])
            if activity.get("date") and activity.get("title")
        ]
        events.extend(
            CalendarEvent(
                event_id=str(activity.get("id", "")),
                title=str(activity.get("title", "")),
                event_date=str(activity.get("due", "")),
                description="Fieldora project activity deadline",
            )
            for activity in self._data.get("project_activities", [])
            if activity.get("due") and activity.get("title")
        )
        return tuple(events)

    def _export_calendar(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export Fieldora calendar", "fieldora-research-calendar.ics",
            "iCalendar (*.ics)",
        )
        if destination:
            CalendarInteropService().export_ics(self._calendar_events(), Path(destination))

    def _selected_calendar_event(self) -> CalendarEvent | None:
        item = self._activities.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Calendar integration", "Select an activity on the chosen date first."
            )
            return None
        activity_id = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (event for event in self._calendar_events() if event.event_id == activity_id),
            None,
        )

    def _open_calendar_provider(self, provider: str) -> None:
        event = self._selected_calendar_event()
        if event is None:
            return
        service = CalendarInteropService()
        url = (
            service.google_create_url(event)
            if provider == "google"
            else service.outlook_create_url(event)
        )
        QDesktopServices.openUrl(QUrl(url))

    def _refresh_calendar(self) -> None:
        if not hasattr(self, "_activities"):
            return
        counts: dict[str, int] = {}
        for activity in self._data.get("activities", []):
            day = str(activity.get("date", ""))
            if day:
                counts[day] = counts.get(day, 0) + 1
        for activity in self._data.get("project_activities", []):
            day = str(activity.get("due", ""))
            if day:
                counts[day] = counts.get(day, 0) + 1
        self._calendar.set_activity_counts(counts)
        selected = self._selected_date()
        self._activities.clear()
        for activity in self._data.get("activities", []):
            if activity.get("date") == selected:
                from PySide6.QtWidgets import QListWidgetItem

                item = QListWidgetItem(str(activity.get("title", "")))
                item.setData(Qt.ItemDataRole.UserRole, activity.get("id"))
                self._activities.addItem(item)
