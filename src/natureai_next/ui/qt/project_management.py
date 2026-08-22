"""Qt Project and Work Management workspace."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from collections.abc import Callable
import json
import sqlite3

from natureai_next.application.workspace_context import WorkspaceContext

from natureai_next.application.project_management import (
    PRIORITIES,
    RECURRENCES,
    ROLE_PERMISSIONS,
    ProjectExportOptions,
    ProjectManagementService,
    TaskSummary,
)

from PySide6.QtCore import QDate, QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QPainter, QPen, QPixmap, QPolygonF, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from natureai_next.ui.qt.activity_calendar import ActivityCountCalendar
from natureai_next.ui.qt.date_time_input import get_datetime_text


KANBAN_TASK_MIME = "application/x-fieldora-task-id"


class KanbanTaskList(QListWidget):
    """Drop target for task cards in one workflow status."""

    task_dropped = Signal(str, str)

    def __init__(self, status_id: str, *, editable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.status_id = status_id
        self.setAcceptDrops(editable)
        self.setDragEnabled(editable)
        self.setDropIndicatorShown(editable)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop if editable
            else QAbstractItemView.DragDropMode.NoDragDrop
        )
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(6)
        self.setMinimumHeight(360)

    def startDrag(self, supported_actions) -> None:  # noqa: N802 - Qt API
        item = self.currentItem()
        if item is None:
            return
        task_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not task_id:
            return
        mime = QMimeData()
        mime.setData(KANBAN_TASK_MIME, task_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasFormat(KANBAN_TASK_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasFormat(KANBAN_TASK_MIME):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not event.mimeData().hasFormat(KANBAN_TASK_MIME):
            event.ignore()
            return
        task_id = bytes(event.mimeData().data(KANBAN_TASK_MIME)).decode("utf-8")
        if task_id:
            self.task_dropped.emit(task_id, self.status_id)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()


class ResearchAreaCanvas(QGraphicsView):
    """Read-only WGS84 overview; editing belongs to the labelled StreetMaps view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(0, 0, 720, 360)
        self.setMinimumHeight(360)
        self._coordinates: list[list[float]] = []
        self._features: tuple[dict, ...] = ()
        self._feature_bounds: QRectF | None = None
        self._redraw()

    @staticmethod
    def _scene_point(longitude: float, latitude: float) -> QPointF:
        return QPointF((longitude + 180) * 2, (90 - latitude) * 2)

    @staticmethod
    def _coordinate(point: QPointF) -> list[float]:
        return [max(-180.0, min(180.0, point.x() / 2 - 180)), max(-90.0, min(90.0, 90 - point.y() / 2))]

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)

    def coordinates(self) -> list[list[float]]:
        return [list(point) for point in self._coordinates]

    def clear_drawing(self) -> None:
        self._coordinates.clear()
        self._redraw()

    def set_features(self, features: tuple[dict, ...]) -> None:
        self._features = features
        self._redraw()

    def _redraw(self) -> None:
        scene = self.scene()
        scene.clear()
        scene.setBackgroundBrush(QBrush(QColor("#e8eee9")))
        grid_pen = QPen(QColor("#c2cec5"), 1)
        for longitude in range(-180, 181, 30):
            x = self._scene_point(longitude, 0).x()
            scene.addLine(x, 0, x, 360, grid_pen)
        for latitude in range(-90, 91, 30):
            y = self._scene_point(0, latitude).y()
            scene.addLine(0, y, 720, y, grid_pen)
        feature_points: list[QPointF] = []
        for feature in self._features:
            ring = feature.get("geometry", {}).get("coordinates", [[]])[0]
            points = [self._scene_point(float(p[0]), float(p[1])) for p in ring]
            feature_points.extend(points)
            polygon = QPolygonF(points)
            scene.addPolygon(polygon, QPen(QColor("#17663c"), 2), QBrush(QColor(47, 143, 91, 70)))
        if self._coordinates:
            points = [self._scene_point(*point) for point in self._coordinates]
            polygon = QPolygonF(points)
            if len(points) >= 3:
                scene.addPolygon(polygon, QPen(QColor("#d26818"), 3), QBrush(QColor(210, 104, 24, 65)))
            else:
                for left, right in zip(points, points[1:]):
                    scene.addLine(left.x(), left.y(), right.x(), right.y(), QPen(QColor("#d26818"), 3))
            for point in points:
                scene.addEllipse(point.x() - 4, point.y() - 4, 8, 8, QPen(QColor("#ffffff")), QBrush(QColor("#d26818")))
        self._feature_bounds = QPolygonF(feature_points).boundingRect() if feature_points else None
        self._fit_research_area()

    def _fit_research_area(self) -> None:
        """Make a local WGS84 area legible instead of showing it at world scale."""
        if self._feature_bounds is not None and not self._feature_bounds.isEmpty():
            # Scene units are twice WGS84 degrees.  A fixed margin (previously
            # 12 units / about six degrees) makes a county-sized boundary look
            # like a dot.  Pad relative to the selected area's own extent.
            extent = max(self._feature_bounds.width(), self._feature_bounds.height())
            padding = max(extent * 0.12, 0.002)
            bounds = self._feature_bounds.adjusted(-padding, -padding, padding, padding)
            self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_research_area()


class StreetMapsSnapshotView(QLabel):
    """Aspect-correct display of the map image saved with a project."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(360)
        self.setText("Save a project snapshot from Library → Maps to show it here.")
        self.setStyleSheet("background:#172521;color:#a9b6b2;")

    def set_snapshot(self, path: str | Path | None) -> None:
        self._source = QPixmap(str(path)) if path and Path(path).is_file() else QPixmap()
        self._render()

    def _render(self) -> None:
        if self._source.isNull():
            self.setPixmap(QPixmap())
            self.setText("The selected StreetMaps snapshot is unavailable.")
            return
        self.setText("")
        size = self.size()
        if size.width() > 0 and size.height() > 0:
            self.setPixmap(
                self._source.scaled(
                    size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._render()


class GanttCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks: tuple[TaskSummary, ...] = ()
        self.setMinimumHeight(300)

    def set_tasks(self, tasks: tuple[TaskSummary, ...]) -> None:
        self._tasks = tuple(item for item in tasks if item.start_date or item.due_date)
        self.setMinimumHeight(max(260, 42 + len(self._tasks) * 32))
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111713"))
        painter.setPen(QColor("#d7e1da"))
        if not self._tasks:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Add task dates to build the Gantt timeline.")
            return
        parsed = []
        for task in self._tasks:
            try:
                start = date.fromisoformat(task.start_date or task.due_date)
                end = date.fromisoformat(task.due_date or task.start_date)
            except ValueError:
                continue
            parsed.append((task, start, max(start, end)))
        if not parsed:
            return
        minimum = min(item[1] for item in parsed)
        maximum = max(item[2] for item in parsed)
        span = max(1, (maximum - minimum).days + 1)
        label_width = min(260, max(150, self.width() // 4))
        chart_width = max(100, self.width() - label_width - 20)
        painter.setPen(QPen(QColor("#2c3a32"), 1))
        for offset in range(0, span, max(1, span // 12)):
            x = label_width + offset / span * chart_width
            painter.drawLine(int(x), 24, int(x), self.height())
        for row, (task, start, end) in enumerate(parsed):
            y = 34 + row * 32
            painter.setPen(QColor("#d7e1da"))
            painter.drawText(8, y + 17, task.title[:36])
            x = label_width + (start - minimum).days / span * chart_width
            width = max(8.0, ((end - start).days + 1) / span * chart_width)
            color = "#dc2626" if task.blocked else "#16a34a" if task.status_category == "done" else "#2563eb"
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, width, 20), 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(x + 4, y, max(0, width - 8), 20), Qt.AlignmentFlag.AlignVCenter, f"{task.progress}%")
        painter.setPen(QColor("#9fb1a5"))
        painter.drawText(label_width, 18, minimum.isoformat())
        painter.drawText(max(label_width, self.width() - 90), 18, maximum.isoformat())


class PhaseTaskTree(QTreeWidget):
    """Hierarchy tree that accepts task drops on phase nodes."""

    task_phase_dropped = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None or str(item.data(0, Qt.ItemDataRole.UserRole + 1) or '') != 'task':
            return
        task_id = str(item.data(0, Qt.ItemDataRole.UserRole) or '')
        if not task_id:
            return
        mime = QMimeData(); mime.setData(KANBAN_TASK_MIME, task_id.encode('utf-8'))
        drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction() if event.mimeData().hasFormat(KANBAN_TASK_MIME) else event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        target = self.itemAt(event.position().toPoint())
        if event.mimeData().hasFormat(KANBAN_TASK_MIME) and target is not None and str(target.data(0, Qt.ItemDataRole.UserRole + 1) or '') == 'phase':
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        target = self.itemAt(event.position().toPoint())
        if target is None or str(target.data(0, Qt.ItemDataRole.UserRole + 1) or '') != 'phase':
            event.ignore(); return
        task_id = bytes(event.mimeData().data(KANBAN_TASK_MIME)).decode('utf-8')
        phase_id = str(target.data(0, Qt.ItemDataRole.UserRole) or '')
        if task_id and phase_id:
            self.task_phase_dropped.emit(task_id, phase_id); event.acceptProposedAction()
        else:
            event.ignore()


class TaskDialog(QDialog):
    def __init__(
        self,
        statuses: tuple[dict, ...],
        *,
        owners: tuple[dict, ...] = (),
        phases: tuple[dict, ...] = (),
        sprints: tuple[dict, ...] = (),
        current_user: str = "",
        parent_task_id: str | None = None,
        milestone: bool = False,
        task: TaskSummary | None = None,
        description: str = "",
        read_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(("View task" if read_only else "Edit task") if task else ("New milestone" if milestone else "New task"))
        self.resize(560, 650)
        self.title = QLineEdit(task.title if task else "")
        self.description = QPlainTextEdit(description)
        self.description.setMaximumHeight(130)
        self.owner = QComboBox()
        self.owner.setEditable(True)
        self.owner.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for row in owners:
            user_id = str(row.get("user_id") or "")
            role = str(row.get("role") or "")
            self.owner.addItem(f"{user_id} ({role})" if role else user_id, user_id)
        desired_owner = task.owner_id if task else current_user
        index = self.owner.findData(desired_owner)
        if index >= 0:
            self.owner.setCurrentIndex(index)
        elif desired_owner:
            self.owner.setEditText(desired_owner)
        self.status = QComboBox()
        for row in statuses:
            self.status.addItem(str(row["name"]), str(row["status_id"]))
        if task:
            status_index = self.status.findData(task.status_id)
            if status_index >= 0:
                self.status.setCurrentIndex(status_index)
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        if task:
            self.priority.setCurrentText(task.priority)
        self.start = QLineEdit(task.start_date if task else "")
        self.start.setPlaceholderText("YYYY-MM-DD")
        self.due = QLineEdit(task.due_date if task else "")
        self.due.setPlaceholderText("YYYY-MM-DD")
        self.estimate = QDoubleSpinBox()
        self.estimate.setRange(0, 100000)
        self.estimate.setSuffix(" h")
        if task:
            self.estimate.setValue(task.estimate_hours)
        self.budget = QDoubleSpinBox()
        self.budget.setRange(0, 1_000_000_000)
        self.realized = QDoubleSpinBox()
        self.realized.setRange(0, 100000)
        self.realized.setSuffix(" h")
        if task:
            self.realized.setValue(task.realized_hours)
        self.phase = QComboBox()
        self.phase.addItem("No phase", None)
        for row in phases:
            self.phase.addItem(str(row["name"]), str(row["phase_id"]))
        if task and task.phase_id:
            index = self.phase.findData(task.phase_id)
            if index >= 0: self.phase.setCurrentIndex(index)
        self.sprint = QComboBox()
        self.sprint.setEditable(True)
        self.sprint.addItem("No sprint", None)
        for row in sprints:
            self.sprint.addItem(str(row["name"]), str(row["sprint_id"]))
        if task and task.sprint_id:
            index = self.sprint.findData(task.sprint_id)
            if index >= 0: self.sprint.setCurrentIndex(index)
        elif task and task.sprint_name:
            self.sprint.setEditText(task.sprint_name)
        self.recurrence = QComboBox()
        self.recurrence.addItems(RECURRENCES)
        self.recurrence_end = QLineEdit()
        self.recurrence_end.setPlaceholderText("YYYY-MM-DD")
        self.milestone = QCheckBox()
        self.milestone.setChecked(task.milestone if task else milestone)
        self.parent_task_id = task.parent_task_id if task else parent_task_id
        form = QFormLayout()
        for label, control in (
            ("Title", self.title), ("Description", self.description), ("Assigned user", self.owner),
            ("Status", self.status), ("Priority", self.priority), ("Start", self.start),
            ("Strict deadline", self.due), ("Manual estimate", self.estimate),
            ("Realized", self.realized), ("Budget", self.budget), ("Phase", self.phase),
            ("Sprint", self.sprint), ("Recurrence", self.recurrence),
            ("Recurrence ends", self.recurrence_end),
            ("Milestone", self.milestone),
        ):
            form.addRow(label, control)
        if read_only:
            for control in (self.title, self.description, self.owner, self.status, self.priority,
                            self.start, self.due, self.estimate, self.realized, self.budget,
                            self.phase, self.sprint, self.recurrence, self.recurrence_end, self.milestone):
                control.setEnabled(False)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.reject)
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, object]:
        owner = str(self.owner.currentData() or self.owner.currentText()).strip()
        if " (" in owner:
            owner = owner.split(" (", 1)[0]
        return {
            "title": self.title.text().strip(),
            "description": self.description.toPlainText().strip(),
            "owner_id": owner,
            "status_id": str(self.status.currentData()),
            "priority": self.priority.currentText(),
            "start_date": self.start.text().strip(),
            "due_date": self.due.text().strip(),
            "estimate_hours": self.estimate.value(),
            "realized_hours": self.realized.value(),
            "budget": self.budget.value(),
            "phase_id": self.phase.currentData(),
            "sprint_id": self.sprint.currentData(),
            "recurrence": self.recurrence.currentText(),
            "recurrence_end": self.recurrence_end.text().strip(),
            "sprint": self.sprint.currentText().strip() if self.sprint.currentData() is None else "",
            "milestone": self.milestone.isChecked(),
            "parent_task_id": self.parent_task_id,
        }


class ProjectManagementWorkspace(QWidget):
    """Complete task, planning, collaboration, capacity, and reporting surface."""

    route_requested = Signal(str)

    def __init__(
        self,
        database_path: Path,
        *,
        actor_provider=None,
        selected_asset_ids: Callable[[], tuple[str, ...]] = tuple,
        library_database_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = ProjectManagementService(database_path)
        self._context = WorkspaceContext.current()
        self._actor_provider = actor_provider or (lambda: self._context.actor_id)
        self._unsubscribe_context = self._context.subscribe(self._context_event)
        self._selected_asset_ids = selected_asset_ids
        self._library_database_path = library_database_path
        self._project_id: str | None = None
        self._task_id: str | None = None
        self._tasks: tuple[TaskSummary, ...] = ()
        self.setObjectName("projectManagementWorkspace")

        self._projects = QListWidget()
        self._projects.setMinimumWidth(220)
        self._projects.currentItemChanged.connect(self._project_selected)
        new_project = QPushButton("New project")
        new_project.clicked.connect(self._new_project)
        template_project = QPushButton("New from template")
        template_project.clicked.connect(self._new_from_template)
        delete_project = QPushButton("Delete project")
        delete_project.clicked.connect(self._delete_project)
        project_panel = QWidget()
        project_layout = QVBoxLayout(project_panel)
        project_layout.addWidget(QLabel("<h3>Projects</h3>"))
        project_layout.addWidget(self._projects, 1)
        project_layout.addWidget(new_project)
        project_layout.addWidget(template_project)
        project_layout.addWidget(delete_project)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tasks_page(), "Project Workspace")
        self._tabs.addTab(self._build_portfolio_page(), "Portfolio & My Work")
        self._tabs.addTab(self._build_board_page(), "Kanban")
        self._tabs.addTab(self._build_grid_page(), "Grid")
        self._tabs.addTab(self._build_gantt_page(), "Gantt")
        self._tabs.addTab(self._build_calendar_page(), "Calendar")
        self._tabs.addTab(self._build_workload_page(), "Workload & Time")
        self._tabs.addTab(self._build_hr_availability_page(), "Availability")
        self._tabs.addTab(self._build_dashboard_page(), "Dashboard")
        self._tabs.addTab(self._build_activity_page(), "Activity")
        self._survey_tab_index = self._tabs.addTab(self._build_surveys_page(), "Surveys & Sampling")
        self._quality_tab_index = self._tabs.addTab(self._build_quality_page(), "Data Quality")
        self._tabs.addTab(self._build_research_area_page(), "Research Area & Media")
        self._tabs.addTab(self._build_research_package_page(), "Research Package")
        self._tabs.addTab(self._build_admin_page(), "Project Settings")
        self._tabs.currentChanged.connect(lambda _index: self.refresh_project())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(project_panel)
        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((240, 1100))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.refresh()

    def _build_tasks_page(self) -> QWidget:
        """Build the clean project/task workspace.

        The left pane is the authoritative hierarchy. Selecting any task or
        subtask updates the contextual workspace on the right. Audit and
        security information deliberately remain outside this user surface.
        """
        page = QWidget()

        self._task_tree = PhaseTaskTree()
        self._task_tree.setHeaderLabels(("Project hierarchy", "Parent task", "Status", "Due"))
        self._task_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._task_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._task_tree.setAlternatingRowColors(True)
        self._task_tree.setMinimumWidth(420)
        self._task_tree.itemSelectionChanged.connect(self._task_selected)
        self._task_tree.itemDoubleClicked.connect(self._hierarchy_double_clicked)
        self._task_tree.task_phase_dropped.connect(self._assign_task_to_phase)

        task_actions = QHBoxLayout()
        for text, slot in (
            ("New task", self._new_task),
            ("New phase", self._new_phase),
            ("New milestone", self._new_milestone),
            ("Change status", self._change_status),
            ("Assign owner", self._assign_owner),
            ("Delete", self._delete_task),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            task_actions.addWidget(button)
        task_actions.addStretch(1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(task_actions)
        left_layout.addWidget(self._task_tree, 1)

        self._task_header = QLabel("<h2>Select a task</h2><p>Choose a phase, task or subtask from the hierarchy.</p>")
        self._task_header.setWordWrap(True)

        self._detail_tabs = QTabWidget()

        self._overview = QTextBrowser()
        self._detail_tabs.addTab(self._overview, "Overview")

        self._comments = QTextBrowser()
        discussion_page = QWidget()
        discussion_layout = QVBoxLayout(discussion_page)
        discussion_layout.addWidget(self._comments, 1)
        discussion_actions = QHBoxLayout()
        add_comment = QPushButton("Add discussion")
        add_comment.clicked.connect(self._add_comment)
        discussion_actions.addWidget(add_comment)
        discussion_actions.addStretch(1)
        discussion_layout.addLayout(discussion_actions)
        self._detail_tabs.addTab(discussion_page, "Discussion")

        self._subtasks = QTreeWidget()
        self._subtasks.setHeaderLabels(("Subtask", "Parent task", "Status", "Owner", "Due"))
        self._subtasks.itemDoubleClicked.connect(
            lambda item, _column: self._open_task(str(item.data(0, Qt.ItemDataRole.UserRole)), edit=True)
        )
        subtask_page = QWidget()
        subtask_layout = QVBoxLayout(subtask_page)
        subtask_layout.addWidget(self._subtasks, 1)
        add_subtask = QPushButton("Add subtask")
        add_subtask.clicked.connect(self._new_subtask)
        subtask_layout.addWidget(add_subtask)
        self._detail_tabs.addTab(subtask_page, "Subtasks")

        self._evidence = QTableWidget(0, 3)
        self._evidence.setHorizontalHeaderLabels(("Type", "Linked item", "Relationship"))
        self._evidence.horizontalHeader().setStretchLastSection(True)
        evidence_page = QWidget()
        evidence_layout = QVBoxLayout(evidence_page)
        evidence_layout.addWidget(self._evidence, 1)
        evidence_layout.addWidget(QLabel("Evidence links include observations, specimens, samples, protocols, laboratory records and library assets."))
        self._detail_tabs.addTab(evidence_page, "Evidence")

        self._attachments = QTableWidget(0, 4)
        self._attachments.setHorizontalHeaderLabels(("Name", "Kind", "Version", "Location"))
        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.addWidget(self._attachments, 1)
        file_actions = QHBoxLayout()
        for text, slot in (("Attach file", self._attach_file), ("Attach link", self._attach_link), ("Add version", self._attach_version)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            file_actions.addWidget(button)
        file_actions.addStretch(1)
        files_layout.addLayout(file_actions)
        self._detail_tabs.addTab(files_page, "Files")

        self._notes = QTextBrowser()
        self._note_entry = QPlainTextEdit()
        self._note_entry.setPlaceholderText("Write a note linked to this task or subtask…")
        self._note_entry.setMaximumHeight(100)
        self._save_note_button = QPushButton("Save note")
        self._save_note_button.clicked.connect(self._save_task_note)
        notes_page = QWidget()
        notes_layout = QVBoxLayout(notes_page)
        notes_layout.addWidget(self._notes, 1)
        notes_layout.addWidget(self._note_entry)
        notes_layout.addWidget(self._save_note_button, 0, Qt.AlignmentFlag.AlignRight)
        self._detail_tabs.addTab(notes_page, "Notes")

        self._time_entries = QTableWidget(0, 5)
        self._time_entries.setHorizontalHeaderLabels(("Date", "User", "Hours", "Description", "ID"))
        time_page = QWidget()
        time_layout = QVBoxLayout(time_page)
        time_layout.addWidget(self._time_entries, 1)
        add_time = QPushButton("Add time entry")
        add_time.clicked.connect(self._log_time)
        time_layout.addWidget(add_time)
        self._detail_tabs.addTab(time_page, "Time")

        self._dependencies = QTableWidget(0, 3)
        self._dependencies.setHorizontalHeaderLabels(("Dependency", "Status", "Type"))
        dependency_page = QWidget()
        dependency_layout = QVBoxLayout(dependency_page)
        dependency_layout.addWidget(self._dependencies, 1)
        add_dependency = QPushButton("Set dependency")
        add_dependency.clicked.connect(self._set_dependency)
        dependency_layout.addWidget(add_dependency)
        self._detail_tabs.addTab(dependency_page, "Dependencies")

        self._activity_detail = QTextBrowser()
        self._detail_tabs.addTab(self._activity_detail, "Activity")

        # Existing checklist/custom-field widgets remain available to the
        # underlying functions but are no longer exposed as top-level tabs.
        self._checklist = QListWidget()
        self._checklist.itemChanged.connect(self._checklist_changed)
        self._custom_values = QTableWidget(0, 3)
        self._custom_values.setHorizontalHeaderLabels(("Field", "Type", "Value"))

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.addWidget(self._task_header)
        right_layout.addWidget(self._detail_tabs, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((480, 900))

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter, 1)
        return page

    def _build_portfolio_page(self) -> QWidget:
        """Build a cross-project portfolio limited by effective project access."""
        page = QWidget()
        root = QVBoxLayout(page)
        self._portfolio_summary = QLabel()
        self._portfolio_summary.setWordWrap(True)
        root.addWidget(self._portfolio_summary)
        self._portfolio_tabs = QTabWidget()
        root.addWidget(self._portfolio_tabs, 1)

        self._portfolio_hierarchy = QTreeWidget()
        self._portfolio_hierarchy.setHeaderLabels(("Project / phase / task", "Owner", "Status", "Estimate", "Realized", "Due"))
        self._portfolio_hierarchy.itemDoubleClicked.connect(self._portfolio_item_opened)
        self._portfolio_tabs.addTab(self._portfolio_hierarchy, "Hierarchy")

        self._portfolio_kanban = QTabWidget()
        self._portfolio_tabs.addTab(self._portfolio_kanban, "Kanban")

        self._portfolio_grid = QTableWidget(0, 12)
        self._portfolio_grid.setHorizontalHeaderLabels(("Project", "Phase", "Task", "Parent", "Sprint", "Owner", "Status", "Priority", "Estimate", "Realized", "Progress", "Due"))
        self._portfolio_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_grid.cellDoubleClicked.connect(self._portfolio_grid_opened)
        self._portfolio_tabs.addTab(self._portfolio_grid, "Grid")

        self._portfolio_gantt = QTableWidget(0, 8)
        self._portfolio_gantt.setHorizontalHeaderLabels(("Project", "Phase", "Task", "Owner", "Start", "Due", "Progress", "Blocked"))
        self._portfolio_gantt.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_tabs.addTab(self._portfolio_gantt, "Gantt")

        self._portfolio_calendar = QTableWidget(0, 7)
        self._portfolio_calendar.setHorizontalHeaderLabels(("Date", "Project", "Phase", "Task / milestone", "Owner", "Status", "Type"))
        self._portfolio_calendar.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_tabs.addTab(self._portfolio_calendar, "Calendar")

        self._portfolio_workload = QTableWidget(0, 12)
        self._portfolio_workload.setHorizontalHeaderLabels(("User", "Projects", "Roles", "Scheduled", "Unavailable", "Organisation", "Allocated", "Remaining", "Tasks", "Open estimate", "Actual", "Utilization"))
        self._portfolio_workload.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_tabs.addTab(self._portfolio_workload, "Workload")

        self._portfolio_resources = QTableWidget(0, 7)
        self._portfolio_resources.setHorizontalHeaderLabels(("User", "Projects", "Roles", "Allocated", "Remaining", "Task count", "Overallocated"))
        self._portfolio_resources.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_tabs.addTab(self._portfolio_resources, "Resources")

        self._portfolio_budget = QTableWidget(0, 8)
        self._portfolio_budget.setHorizontalHeaderLabels(("Project", "Phases", "Tasks", "Planned budget", "Realized budget", "Variance", "Estimate", "Realized hours"))
        self._portfolio_budget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._portfolio_tabs.addTab(self._portfolio_budget, "Budget")

        refresh = QPushButton("Refresh portfolio")
        refresh.clicked.connect(self._refresh_portfolio)
        root.addWidget(refresh, 0, Qt.AlignmentFlag.AlignRight)
        return page

    def _portfolio_item_opened(self, item: QTreeWidgetItem, _column: int) -> None:
        task_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        project_id = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or "")
        if project_id:
            self.select_project(project_id)
        if task_id:
            self._open_task(task_id, edit=True)

    def _portfolio_grid_opened(self, row: int, _column: int) -> None:
        item = self._portfolio_grid.item(row, 0)
        if item is None:
            return
        project_id = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
        task_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if project_id:
            self.select_project(project_id)
        if task_id:
            self._open_task(task_id, edit=True)

    @staticmethod
    def _set_table_row(table: QTableWidget, row: int, values: tuple[object, ...]) -> None:
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(str(value)))

    def _refresh_portfolio(self) -> None:
        if not hasattr(self, "_portfolio_tabs"):
            return
        actor = str(self._actor_provider() or "local-user")
        snapshot = self._service.portfolio_snapshot(actor)
        projects = tuple(snapshot["projects"])
        phases = tuple(snapshot["phases"])
        tasks = tuple(snapshot["tasks"])
        workload = tuple(snapshot["workload"])
        summary = dict(snapshot["summary"])
        self._portfolio_summary.setText(
            "<h2>Portfolio & My Work</h2>"
            f"<p><b>{summary['project_count']}</b> accessible projects · "
            f"<b>{summary['phase_count']}</b> phases · <b>{summary['task_count']}</b> tasks · "
            f"effective estimate <b>{summary['effective_estimate_hours']:.2f} h</b> · "
            f"realized <b>{summary['realized_hours']:.2f} h</b></p>"
        )
        self._portfolio_hierarchy.clear()
        tasks_by_project: dict[str, list[dict]] = {}
        for task in tasks:
            tasks_by_project.setdefault(str(task["project_id"]), []).append(dict(task))
        phases_by_project: dict[str, list[dict]] = {}
        for phase in phases:
            phases_by_project.setdefault(str(phase["project_id"]), []).append(dict(phase))
        for project in projects:
            project_id = str(project["project_id"])
            root = QTreeWidgetItem((str(project["name"]), str(project.get("owner_id") or ""), str(project.get("status") or ""), f"{project.get('effective_estimate_hours',0):.2f}", f"{project.get('realized_hours',0):.2f}", str(project.get("due_date") or "")))
            root.setData(0, Qt.ItemDataRole.UserRole + 1, project_id)
            self._portfolio_hierarchy.addTopLevelItem(root)
            project_tasks = tasks_by_project.get(project_id, [])
            by_parent: dict[str | None, list[dict]] = {}
            for task in project_tasks:
                by_parent.setdefault(task.get("parent_task_id"), []).append(task)
            phase_nodes: dict[str, QTreeWidgetItem] = {}
            for phase in phases_by_project.get(project_id, []):
                node = QTreeWidgetItem((str(phase["name"]), "", "Phase", f"{float(phase.get('effective_estimate_hours') or 0):.2f}", f"{float(phase.get('calculated_realized_hours') or 0):.2f}", ""))
                node.setData(0, Qt.ItemDataRole.UserRole + 1, project_id)
                root.addChild(node); phase_nodes[str(phase["phase_id"])] = node
            unassigned = QTreeWidgetItem(("Unassigned phase", "", "Phase", "", "", ""))
            unassigned.setData(0, Qt.ItemDataRole.UserRole + 1, project_id)
            if any(not task.get("phase_id") for task in project_tasks):
                root.addChild(unassigned)
            def append_task(parent_node: QTreeWidgetItem, task: dict) -> None:
                node = QTreeWidgetItem((str(task["title"]), str(task["owner_id"]), str(task["status_name"]), f"{float(task['effective_estimate_hours']):.2f}", f"{float(task['realized_hours']):.2f}", str(task["due_date"] or "")))
                node.setData(0, Qt.ItemDataRole.UserRole, str(task["task_id"])); node.setData(0, Qt.ItemDataRole.UserRole + 1, project_id)
                parent_node.addChild(node)
                for child in by_parent.get(str(task["task_id"]), []): append_task(node, child)
            for task in by_parent.get(None, []):
                append_task(phase_nodes.get(str(task.get("phase_id")), unassigned), task)
            root.setExpanded(True)

        statuses = sorted({str(task["status_name"]) for task in tasks})
        while self._portfolio_kanban.count():
            widget = self._portfolio_kanban.widget(0); self._portfolio_kanban.removeTab(0); widget.deleteLater()
        for status in statuses:
            table = QTableWidget(0, 6); table.setHorizontalHeaderLabels(("Project", "Phase", "Task", "Owner", "Estimate", "Due")); table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            status_tasks = [task for task in tasks if str(task["status_name"]) == status]
            table.setRowCount(len(status_tasks))
            for row, task in enumerate(status_tasks):
                self._set_table_row(table, row, (task["project_name"], task["phase_name"] or "Unassigned", task["title"], task["owner_id"], f"{float(task['effective_estimate_hours']):.2f}", task["due_date"]))
            self._portfolio_kanban.addTab(table, f"{status} ({len(status_tasks)})")

        self._portfolio_grid.setRowCount(len(tasks))
        self._portfolio_gantt.setRowCount(len(tasks))
        calendar_rows = []
        for row, task in enumerate(tasks):
            parent = next((t["title"] for t in tasks if t["task_id"] == task.get("parent_task_id")), "")
            self._set_table_row(self._portfolio_grid, row, (task["project_name"], task["phase_name"] or "Unassigned", task["title"], parent, task["sprint_name"], task["owner_id"], task["status_name"], task["priority"], f"{float(task['effective_estimate_hours']):.2f}", f"{float(task['realized_hours']):.2f}", f"{task['progress']}%", task["due_date"]))
            self._portfolio_grid.item(row, 0).setData(Qt.ItemDataRole.UserRole, task["task_id"]); self._portfolio_grid.item(row, 0).setData(Qt.ItemDataRole.UserRole + 1, task["project_id"])
            self._set_table_row(self._portfolio_gantt, row, (task["project_name"], task["phase_name"] or "Unassigned", task["title"], task["owner_id"], task["start_date"], task["due_date"], f"{task['progress']}%", "Yes" if task["blocked"] else "No"))
            if task["start_date"]: calendar_rows.append((task["start_date"], task, "Start"))
            if task["due_date"]: calendar_rows.append((task["due_date"], task, "Due" if not task["milestone"] else "Milestone"))
        calendar_rows.sort(key=lambda row: (row[0], str(row[1]["project_name"]), str(row[1]["title"])))
        self._portfolio_calendar.setRowCount(len(calendar_rows))
        for row, (when, task, kind) in enumerate(calendar_rows):
            self._set_table_row(self._portfolio_calendar, row, (when, task["project_name"], task["phase_name"] or "Unassigned", task["title"], task["owner_id"], task["status_name"], kind))

        self._portfolio_workload.setRowCount(len(workload)); self._portfolio_resources.setRowCount(len(workload))
        for row, item in enumerate(workload):
            scheduled = float(item["scheduled_hours"]); open_estimate = float(item["open_estimate_hours"])
            utilization = 0.0 if scheduled <= 0 else open_estimate / scheduled * 100
            unavailable = float(item["absence_hours"])
            self._set_table_row(self._portfolio_workload, row, (item["user_id"], item["projects"], item["roles"], f"{scheduled:.2f}", f"{unavailable:.2f}", f"{float(item['organisational_hours']):.2f}", f"{float(item['allocated_hours']):.2f}", f"{float(item['remaining_hours']):.2f}", item["task_count"], f"{open_estimate:.2f}", f"{float(item['actual_hours']):.2f}", f"{utilization:.1f}%"))
            self._set_table_row(self._portfolio_resources, row, (item["user_id"], item["projects"], item["roles"], f"{float(item['allocated_hours']):.2f}", f"{float(item['remaining_hours']):.2f}", item["task_count"], "Yes" if float(item["remaining_hours"]) < 0 else "No"))
        self._portfolio_budget.setRowCount(len(projects))
        for row, project in enumerate(projects):
            self._set_table_row(self._portfolio_budget, row, (project["name"], project["phase_count"], project["task_count"], f"{float(project.get('budget') or 0):.2f}", f"{float(project.get('realized_budget') or 0):.2f}", f"{float(project.get('budget_variance') or 0):.2f}", f"{float(project.get('effective_estimate_hours') or 0):.2f}", f"{float(project.get('realized_hours') or 0):.2f}"))

    def _build_board_page(self) -> QWidget:
        page = QWidget()
        self._kanban_host = QWidget()
        self._kanban_layout = QHBoxLayout(self._kanban_host)
        self._kanban_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._kanban_host)
        layout = QVBoxLayout(page)
        layout.addWidget(scroll)
        return page

    def _build_grid_page(self) -> QWidget:
        page = QWidget()
        self._grid = QTableWidget(0, 17)
        self._grid.setHorizontalHeaderLabels(
            ("ID", "Task", "Parent", "Phase", "Sprint", "Owner", "Status", "Priority",
             "Start", "Due", "Manual estimate", "Calculated estimate", "Effective estimate",
             "Realized", "Actual logged", "Progress", "Blocked")
        )
        self._grid.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        export = QPushButton("Export CSV…")
        export.clicked.connect(self._export_csv)
        export_excel = QPushButton("Export Excel…")
        export_excel.clicked.connect(self._export_excel)
        export_pdf = QPushButton("Export PDF report…")
        export_pdf.clicked.connect(self._export_pdf)
        actions = QHBoxLayout()
        actions.addWidget(export)
        actions.addWidget(export_excel)
        actions.addWidget(export_pdf)
        actions.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(actions)
        layout.addWidget(self._grid)
        return page

    def _build_gantt_page(self) -> QWidget:
        page = QWidget()
        self._gantt = GanttCanvas()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._gantt)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Task dates, overlaps, milestones, and dependency blocks"))
        layout.addWidget(scroll)
        return page

    def _build_calendar_page(self) -> QWidget:
        page = QWidget()
        self._calendar = ActivityCountCalendar()
        self._calendar.selectionChanged.connect(self._refresh_calendar)
        self._calendar_items = QListWidget()
        self._calendar_scope = QComboBox()
        self._calendar_scope.addItem("My assigned tasks and activities", "mine")
        self._calendar_scope.addItem("Whole project calendar", "project")
        self._calendar_scope.currentIndexChanged.connect(self._refresh_calendar)
        add_holiday = QPushButton("Add public holiday")
        add_holiday.clicked.connect(self._add_public_holiday)
        splitter = QSplitter()
        splitter.addWidget(self._calendar)
        splitter.addWidget(self._calendar_items)
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("View"))
        controls.addWidget(self._calendar_scope)
        controls.addStretch(1)
        controls.addWidget(add_holiday)
        layout.addLayout(controls)
        layout.addWidget(splitter)
        return page

    def _build_workload_page(self) -> QWidget:
        page = QWidget()
        self._workload = QTableWidget(0, 10)
        self._workload.setHorizontalHeaderLabels(
            ("User", "Role", "Scheduled", "Unavailable", "Organisation", "Allocated",
             "Remaining", "Tasks", "Open estimate", "Actual")
        )
        log_time = QPushButton("Log time on selected task")
        log_time.clicked.connect(self._log_time)
        actions = QHBoxLayout()
        actions.addWidget(log_time)
        actions.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(actions)
        layout.addWidget(self._workload)
        return page

    def _build_hr_availability_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        info = QLabel("Work schedules, leave/PTO/absence, organisational obligations and project allocations are date/time-based. Project users see availability impact; HR/private details remain governed.")
        info.setWordWrap(True); layout.addWidget(info)
        self._availability = QTableWidget(0, 7)
        self._availability.setHorizontalHeaderLabels(("User","Scheduled","Absence","Organisation","Allocated","Remaining","Status"))
        layout.addWidget(self._availability)
        actions=QHBoxLayout()
        for text,handler in (("Assign schedule",self._assign_schedule),("Register absence",self._register_absence),("Add organisational obligation",self._add_obligation),("Allocate to project",self._allocate_user)):
            button=QPushButton(text); button.clicked.connect(handler); actions.addWidget(button)
        actions.addStretch(1); layout.addLayout(actions)
        return page

    def _choose_member(self, title: str) -> str | None:
        if not self._project_id: return None
        members=[str(r['user_id']) for r in self._service.project_members(self._project_id)]
        value,ok=QInputDialog.getItem(self,title,"User",members,0,True)
        return str(value).strip() if ok and str(value).strip() else None

    def _assign_schedule(self) -> None:
        user=self._choose_member("Assign work schedule")
        if not user: return
        templates=self._service.schedule_templates(); labels=[str(t['name']) for t in templates]
        label,ok=QInputDialog.getItem(self,"Work schedule","Template",labels,0,False)
        if not ok: return
        template=next(t for t in templates if t['name']==label)
        start,ok=get_datetime_text(self,"Work schedule","Effective from",include_time=False)
        if ok: self._service.assign_work_schedule(user,template['template_id'],start,actor_id=self._actor_provider()); self.refresh_project()

    def _register_absence(self) -> None:
        user=self._choose_member("Register absence")
        if not user: return
        start,ok=get_datetime_text(self,"Absence","Start date and time",include_time=True)
        if not ok: return
        end,ok=get_datetime_text(self,"Absence","End date and time",include_time=True)
        if not ok: return
        kind,ok=QInputDialog.getItem(self,"Absence","Type",("annual_leave","pto","sick_leave","medical_appointment","other"),0,False)
        if ok: self._service.add_absence(user,start,end,str(kind),actor_id=self._actor_provider()); self.refresh_project()

    def _add_obligation(self) -> None:
        user=self._choose_member("Organisational obligation")
        if not user: return
        start,ok=get_datetime_text(self,"Organisational obligation","Start date and time",include_time=True)
        if not ok: return
        end,ok=get_datetime_text(self,"Organisational obligation","End date and time",include_time=True)
        if not ok: return
        title,ok=QInputDialog.getText(self,"Organisational obligation","Meeting, seminar or obligation")
        if ok and title.strip(): self._service.add_organisational_obligation(user,start,end,"organisation",title,actor_id=self._actor_provider()); self.refresh_project()

    def _allocate_user(self) -> None:
        user=self._choose_member("Project allocation")
        if not user or not self._project_id: return
        hours,ok=QInputDialog.getDouble(self,"Project allocation","Hours per week",0,0,168,2)
        if not ok: return
        start,ok=get_datetime_text(self,"Project allocation","Effective from",include_time=False)
        if ok: self._service.set_project_allocation(user,self._project_id,start,hours_per_week=hours,actor_id=self._actor_provider()); self.refresh_project()

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        self._dashboard_cards = QLabel()
        self._dashboard_cards.setWordWrap(True)
        self._dashboard_table = QTableWidget(0, 2)
        self._dashboard_table.setHorizontalHeaderLabels(("Metric", "Value"))
        self._agile = QTextBrowser()
        layout = QVBoxLayout(page)
        layout.addWidget(self._dashboard_cards)
        layout.addWidget(self._dashboard_table)
        layout.addWidget(QLabel("<b>Agile metrics</b>"))
        layout.addWidget(self._agile)
        return page

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        self._activity = QTableWidget(0, 5)
        self._activity.setHorizontalHeaderLabels(("Time", "Actor", "Event", "Task", "Details"))
        self._notifications = QListWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<b>Chronological audit activity</b>"))
        layout.addWidget(self._activity, 3)
        layout.addWidget(QLabel("<b>My due notifications and @mentions</b>"))
        layout.addWidget(self._notifications, 1)
        return page

    def _build_surveys_page(self) -> QWidget:
        return self._build_operations_link_page(
            "Surveys & Sampling",
            "Survey protocols, events, detections, non-detections and specimen encounters are managed in the current Research Operations workspace.",
            "Survey events",
        )

    def _build_measurements_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        intro = QLabel("Manage specimen and environmental measurements, samples, custody, laboratory work, calibration and uncertainty."); intro.setWordWrap(True); layout.addWidget(intro)
        actions = QHBoxLayout()
        for text, slot in (("New definition…", self._new_measurement_definition), ("Animal templates…", self._install_measurement_template), ("New sample…", self._new_sample), ("Record measurement…", self._new_measurement), ("Import instrument CSV…", self._import_measurements_csv), ("Custody event…", self._new_custody), ("Laboratory record…", self._new_lab_record)):
            button = QPushButton(text); button.clicked.connect(slot); actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions)
        self._samples_table = QTableWidget(0, 8); self._samples_table.setHorizontalHeaderLabels(("Sample ID","Specimen","Type","Collected","Coordinates","Container","Preservation","Status")); layout.addWidget(QLabel("<b>Samples and specimens</b>")); layout.addWidget(self._samples_table)
        self._sample_ids = []
        self._measurements_table = QTableWidget(0, 9); self._measurements_table.setHorizontalHeaderLabels(("Sample","Measurement","Category","Value","Unit","Time","Instrument","Calibration","Uncertainty")); layout.addWidget(QLabel("<b>Measurements</b>")); layout.addWidget(self._measurements_table)
        return page

    def _build_quality_page(self) -> QWidget:
        return self._build_operations_link_page(
            "Data Quality",
            "Research data-quality checks and findings are managed in the current Research Operations workspace, where the same project permissions and audit rules are enforced.",
            "Data quality",
        )

    def _build_operations_link_page(self, title: str, description: str, section: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(f"<h3>{title}</h3>")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        open_button = QPushButton(f"Open {title} in Research Operations")
        open_button.setObjectName(f"openResearchOperations{section.replace(' ', '')}")
        open_button.clicked.connect(lambda _checked=False, value=section: self._open_research_operations(value))
        layout.addWidget(heading)
        layout.addWidget(description_label)
        layout.addWidget(open_button)
        layout.addStretch(1)
        return page

    def _open_research_operations(self, section: str) -> None:
        if not self._project_id:
            QMessageBox.information(self, "Project required", "Select a project first.")
            return
        prefix = {
            "Survey events": "__project_surveys__:",
            "Samples": "__project_measurements__:",
            "Data quality": "__project_quality__:",
        }.get(section, "__project_measurements__:")
        self.route_requested.emit(prefix + self._project_id)

    def _build_research_area_page(self) -> QWidget:
        page = QWidget()
        self._research_map = ResearchAreaCanvas(page)
        self._snapshot_view = StreetMapsSnapshotView(page)
        self._research_views = QTabWidget(page)
        self._research_views.addTab(self._research_map, "Boundary overview")
        self._research_views.addTab(self._snapshot_view, "StreetMaps snapshot")
        self._research_areas = QListWidget()
        self._research_areas.currentItemChanged.connect(self._research_area_selected)
        self._project_media = QTableWidget(0, 3)
        self._map_snapshots = QListWidget()
        self._map_snapshots.currentItemChanged.connect(self._map_snapshot_selected)
        self._project_media.setHorizontalHeaderLabels(("Type", "Asset", "Note"))
        draw_help = QLabel(
            "Draw project boundaries directly on Library → Maps, where streets and place names remain visible. "
            "Use Draw Project Area, Finish & Attach, and Save Project Snapshot there; then refresh this project."
        )
        draw_help.setWordWrap(True)
        actions = QHBoxLayout()
        for text, slot in (
            ("Refresh from Maps", self._refresh_research),
            ("Show all boundaries", self._show_all_research_areas),
            ("Import polygon GeoJSON…", self._import_research_area),
            ("Export selected GeoJSON…", self._export_research_area),
            ("Delete area", self._delete_research_area),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        media_actions = QHBoxLayout()
        attach = QPushButton("Attach selected Library media")
        attach.clicked.connect(self._attach_selected_project_media)
        note = QPushButton("Add project note…")
        note.clicked.connect(self._add_project_note)
        media_actions.addWidget(attach)
        media_actions.addWidget(note)
        media_actions.addStretch(1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("<b>Saved research areas</b>"))
        right_layout.addWidget(self._research_areas, 1)
        right_layout.addWidget(QLabel("<b>StreetMaps snapshots</b>"))
        right_layout.addWidget(self._map_snapshots, 1)
        right_layout.addLayout(media_actions)
        right_layout.addWidget(QLabel("<b>Related images, sounds, videos and documents</b>"))
        right_layout.addWidget(self._project_media, 2)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        map_panel = QWidget()
        map_layout = QVBoxLayout(map_panel)
        map_layout.addWidget(draw_help)
        map_layout.addWidget(self._research_views, 1)
        map_layout.addLayout(actions)
        splitter.addWidget(map_panel)
        splitter.addWidget(right)
        splitter.setSizes((800, 420))
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def _build_research_package_page(self) -> QWidget:
        page = QWidget()
        text = QLabel(
            "Create a structured ZIP with JSON data, GeoJSON research maps, CSV media index, "
            "offline HTML index, and selected original files. Audio and video can be playable in the index."
        )
        text.setWordWrap(True)
        self._package_options: dict[str, QCheckBox] = {}
        form = QVBoxLayout()
        for key, label, checked in (
            ("include_project", "Project metadata", True),
            ("include_tasks", "Tasks, milestones, comments, checklists, time and planning data", True),
            ("include_notes", "Project notes", True),
            ("include_research_areas", "Research map and GeoJSON", True),
            ("include_map_snapshots", "StreetMaps snapshots", True),
            ("include_media_index", "Related-media index", True),
            ("include_original_media", "Copy selected original images, audio, video and documents", False),
            ("include_task_attachments", "Copy locally available task attachments", True),
            ("embed_audio_video", "Add playable audio and video controls to the offline HTML index", False),
            ("include_activity", "Project activity history", True),
            ("include_surveys", "Survey protocols, events, effort, detections and non-detections", True),
            ("include_measurements_samples", "Measurements, specimens, samples and laboratory records", True),
            ("include_quality_audit", "Data-quality findings, explanations and dismissals", True),
        ):
            option = QCheckBox(label)
            option.setChecked(checked)
            self._package_options[key] = option
            form.addWidget(option)
        export = QPushButton("Export structured research package…")
        export.clicked.connect(self._export_research_package)
        layout = QVBoxLayout(page)
        layout.addWidget(text)
        layout.addLayout(form)
        layout.addWidget(export, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_admin_page(self) -> QWidget:
        page = QWidget()
        self._statuses = QTableWidget(0, 5)
        self._statuses.setHorizontalHeaderLabels(("Status", "Category", "Color", "Order", "WIP limit"))
        self._members = QTableWidget(0, 2)
        self._members.setHorizontalHeaderLabels(("User", "Role"))
        add_status = QPushButton("Add custom status")
        add_status.clicked.connect(self._add_status)
        add_member = QPushButton("Add / change member role")
        add_member.clicked.connect(self._set_member_role)
        custom_field = QPushButton("Add custom task field")
        custom_field.clicked.connect(self._add_custom_field)
        save_template = QPushButton("Save as project template")
        save_template.clicked.connect(self._save_template)
        portal = QPushButton("Preview client portal")
        portal.clicked.connect(self._preview_portal)
        recur = QPushButton("Create due recurring tasks")
        recur.clicked.connect(self._materialize_recurring)
        actions = QHBoxLayout()
        for button in (add_status, add_member, custom_field, save_template, portal, recur):
            actions.addWidget(button)
        actions.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(actions)
        layout.addWidget(QLabel("<b>Workflow statuses</b>"))
        layout.addWidget(self._statuses)
        layout.addWidget(QLabel("<b>Project RBAC members</b>"))
        layout.addWidget(self._members)
        return page

    def refresh(self) -> None:
        selected = self._project_id
        self._projects.clear()
        actor = str(self._actor_provider() or "local-user")
        for project in self._context.accessible_projects(self._service, permission="view"):
            item = QListWidgetItem(f"{project['name']}\n{project['status']} · due {project.get('due_date') or 'not set'}")
            item.setData(Qt.ItemDataRole.UserRole, project['project_id'])
            self._projects.addItem(item)
            if project['project_id'] == selected:
                self._projects.setCurrentItem(item)
        if self._projects.currentRow() < 0 and self._projects.count():
            self._projects.setCurrentRow(0)

    def _context_event(self, event) -> None:
        if event.source == "project-management":
            return
        if event.topic in {"identity.changed", "permissions.changed"}:
            self.refresh(); self._refresh_portfolio()
        elif event.topic == "project.changed" and event.project_id:
            self.select_project(event.project_id)
        elif event.topic == "data.changed":
            self._refresh_portfolio()
            if not event.project_id or event.project_id == self._project_id:
                self.refresh_project()

    def refresh_project(self) -> None:
        self._refresh_portfolio()
        if not self._project_id:
            return
        self._tasks = self._service.tasks(self._project_id)
        self._refresh_task_table()
        self._refresh_kanban()
        self._refresh_grid()
        self._gantt.set_tasks(self._tasks)
        self._refresh_calendar()
        self._refresh_workload()
        self._refresh_dashboard()
        self._refresh_activity()
        self._refresh_surveys()
        self._refresh_measurements()
        self._refresh_quality()
        self._refresh_research()
        self._refresh_admin()

    def _refresh_measurements(self) -> None:
        if not hasattr(self, "_samples_table") or not self._project_id: return
        samples = self._service.samples(self._project_id); self._sample_ids = [row["sample_id"] for row in samples]; self._samples_table.setRowCount(len(samples))
        for r,row in enumerate(samples):
            values=(row["sample_code"],row["specimen_code"],row["sample_type"],row["collected_at"],f'{row["latitude"] or "—"}, {row["longitude"] or "—"}',row["container"],row["preservation"],row["status"])
            for c,v in enumerate(values): self._samples_table.setItem(r,c,QTableWidgetItem(str(v)))
        measurements=self._service.measurements(self._project_id); self._measurements_table.setRowCount(len(measurements))
        for r,row in enumerate(measurements):
            values=(row["sample_code"] or "Project",row["name"],row["category"],row["value_text"],row["unit"],row["measured_at"],row["instrument"],row["calibration_reference"],row["uncertainty"] if row["uncertainty"] is not None else "—")
            for c,v in enumerate(values): self._measurements_table.setItem(r,c,QTableWidgetItem(str(v)))

    def _selected_sample(self):
        row=self._samples_table.currentRow(); return self._sample_ids[row] if 0 <= row < len(self._sample_ids) else None

    def _install_measurement_template(self):
        if not self._project_id: return
        templates = {
            "Mammal morphometrics": (("Body mass", "mammal", "kg", 0, 100000), ("Head-body length", "mammal", "mm", 0, 20000), ("Tail length", "mammal", "mm", 0, 10000), ("Hind foot length", "mammal", "mm", 0, 3000), ("Ear length", "mammal", "mm", 0, 2000), ("Shoulder height", "mammal", "cm", 0, 1000), ("Chest girth", "mammal", "cm", 0, 3000)),
            "Bird biometrics": (("Body mass", "bird", "g", 0, 300000), ("Wing chord", "bird", "mm", 0, 3000), ("Wingspan", "bird", "mm", 0, 5000), ("Tarsus length", "bird", "mm", 0, 1000), ("Bill length", "bird", "mm", 0, 1000), ("Tail length", "bird", "mm", 0, 3000)),
            "Marine animal morphometrics": (("Total length", "marine animal", "cm", 0, 5000), ("Fork length", "marine animal", "cm", 0, 5000), ("Standard length", "marine animal", "cm", 0, 5000), ("Body mass", "marine animal", "kg", 0, 200000), ("Body girth", "marine animal", "cm", 0, 5000), ("Carapace length", "marine animal", "cm", 0, 1000), ("Flipper length", "marine animal", "cm", 0, 2000), ("Observation depth", "marine animal", "m", 0, 12000)),
        }
        label, ok = QInputDialog.getItem(self, "Measurement templates", "Install definitions for", tuple(templates), 0, False)
        if not ok: return
        existing = {(str(row["name"]).casefold(), str(row["unit"]).casefold()) for row in self._service.measurement_definitions(self._project_id)}
        created = 0
        try:
            for name, category, unit, minimum, maximum in templates[label]:
                if (name.casefold(), unit.casefold()) in existing: continue
                self._service.create_measurement_definition(self._project_id, name=name, category=category, unit=unit, minimum=minimum, maximum=maximum, actor_id=self._actor_provider())
                created += 1
        except Exception as exc: QMessageBox.warning(self, "Measurement templates", str(exc)); return
        self._refresh_measurements()
        QMessageBox.information(self, "Measurement templates", f"Installed {created} definition(s) for {label}.")

    def _new_measurement_definition(self):
        if not self._project_id:return
        name,ok=QInputDialog.getText(self,"Measurement definition","Name (for example salinity, weight or turbidity)");
        if not ok or not name.strip():return
        category,ok=QInputDialog.getItem(self,"Measurement definition","Category",("morphology","water","soil","vegetation","laboratory","other"),0,True);
        if not ok:return
        unit,ok=QInputDialog.getText(self,"Measurement definition","Unit");
        if not ok or not unit.strip():return
        minimum,ok=QInputDialog.getDouble(self,"Measurement definition","Expected minimum",0,-1e12,1e12,4); 
        if not ok:return
        maximum,ok=QInputDialog.getDouble(self,"Measurement definition","Expected maximum",100,-1e12,1e12,4);
        if not ok:return
        try:self._service.create_measurement_definition(self._project_id,name=name,category=category,unit=unit,minimum=minimum,maximum=maximum,actor_id=self._actor_provider())
        except Exception as exc:QMessageBox.warning(self,"Measurement definition",str(exc));return
        self._refresh_measurements()

    def _new_sample(self):
        if not self._project_id:return
        code,ok=QInputDialog.getText(self,"Sample","Unique sample identifier");
        if not ok or not code.strip():return
        kind,ok=QInputDialog.getItem(self,"Sample","Type",("specimen","water","soil","vegetation","tissue","other"),0,True);
        if not ok:return
        specimen,ok=QInputDialog.getText(self,"Sample","Specimen identifier (optional)");
        if not ok:return
        when,ok=get_datetime_text(self,"Sample","Collected date/time",value=datetime.now().strftime("%Y-%m-%d %H:%M"));
        if not ok:return
        container,ok=QInputDialog.getText(self,"Sample","Collection container");
        if not ok:return
        preservation,ok=QInputDialog.getText(self,"Sample","Preservation method");
        if not ok:return
        self._service.create_sample(self._project_id,sample_code=code,sample_type=kind,specimen_code=specimen,collected_at=when,container=container,preservation=preservation,collector=self._actor_provider(),actor_id=self._actor_provider());self._refresh_measurements()

    def _new_measurement(self):
        if not self._project_id:return
        definitions=self._service.measurement_definitions(self._project_id)
        if not definitions:QMessageBox.information(self,"Measurement","Create a measurement definition first.");return
        labels=[f'{row["name"]} ({row["unit"]})' for row in definitions]; label,ok=QInputDialog.getItem(self,"Measurement","Definition",labels,0,False)
        if not ok:return
        definition=definitions[labels.index(label)]; value,ok=QInputDialog.getText(self,"Measurement","Value")
        if not ok:return
        instrument,ok=QInputDialog.getText(self,"Measurement","Instrument");
        if not ok:return
        calibration,ok=QInputDialog.getText(self,"Measurement","Calibration reference");
        if not ok:return
        uncertainty,ok=QInputDialog.getDouble(self,"Measurement","Uncertainty",0,0,1e12,6);
        if not ok:return
        self._service.record_measurement(self._project_id,name=definition["name"],category=definition["category"],value=value,unit=definition["unit"],definition_id=definition["definition_id"],sample_id=self._selected_sample(),instrument=instrument,calibration_reference=calibration,uncertainty=uncertainty,measured_at=datetime.now().isoformat(timespec="minutes"),actor_id=self._actor_provider());self._refresh_measurements()

    def _import_measurements_csv(self):
        if not self._project_id:return
        path,_=QFileDialog.getOpenFileName(self,"Import instrument measurements","","CSV (*.csv)")
        if path:
            try:count=self._service.import_instrument_csv(self._project_id,Path(path),actor_id=self._actor_provider());QMessageBox.information(self,"Instrument import",f"Imported {count} measurement(s).")
            except Exception as exc:QMessageBox.warning(self,"Instrument import",str(exc))
            self._refresh_measurements()

    def _new_custody(self):
        sample=self._selected_sample()
        if not sample:QMessageBox.information(self,"Chain of custody","Select a sample first.");return
        action,ok=QInputDialog.getText(self,"Chain of custody","Action / transfer");
        if not ok:return
        recipient,ok=QInputDialog.getText(self,"Chain of custody","Transferred to");
        if ok:self._service.add_custody_event(sample,action=action,to_party=recipient,occurred_at=datetime.now().isoformat(timespec="minutes"),actor_id=self._actor_provider())

    def _new_lab_record(self):
        sample=self._selected_sample()
        if not sample:QMessageBox.information(self,"Laboratory","Select a sample first.");return
        test,ok=QInputDialog.getText(self,"Laboratory request","Requested test");
        if not ok:return
        laboratory,ok=QInputDialog.getText(self,"Laboratory request","Laboratory");
        if ok:self._service.add_laboratory_record(sample,record_type="request",requested_test=test,laboratory=laboratory,recorded_at=datetime.now().isoformat(timespec="minutes"),actor_id=self._actor_provider())

    def _refresh_quality(self):
        if not hasattr(self,"_quality_table") or not self._project_id:return
        rows=self._service.quality_findings(self._project_id);self._quality_ids=[row["finding_id"] for row in rows];self._quality_table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            values=(row["state"],row["severity"],row["title"],row["entity_type"],row["entity_id"],row["explanation"],row["dismissed_reason"])
            for c,v in enumerate(values):self._quality_table.setItem(r,c,QTableWidgetItem(str(v)))

    def _run_quality_checks(self):
        if self._project_id:self._service.run_quality_checks(self._project_id,actor_id=self._actor_provider());self._refresh_quality()

    def _dismiss_quality(self):
        row=self._quality_table.currentRow()
        if not 0 <= row < len(self._quality_ids):return
        reason,ok=QInputDialog.getMultiLineText(self,"Dismiss quality warning","Reason (stored in the audit history)")
        if ok and reason.strip():self._service.dismiss_quality_finding(self._quality_ids[row],reason=reason,actor_id=self._actor_provider());self._refresh_quality()

    def _refresh_research(self) -> None:
        if not hasattr(self, "_research_areas") or not self._project_id:
            return
        areas = self._service.research_areas(self._project_id)
        self._research_areas.clear()
        for area in areas:
            item = QListWidgetItem(str(area["name"]))
            item.setData(Qt.ItemDataRole.UserRole, str(area["area_id"]))
            item.setData(Qt.ItemDataRole.UserRole + 1, area["feature"])
            self._research_areas.addItem(item)
        self._research_map.set_features(tuple(area["feature"] for area in areas))
        self._map_snapshots.clear()
        snapshots = self._service.map_snapshots(self._project_id)
        for snapshot in snapshots:
            item = QListWidgetItem(f"{snapshot['name']}\n{snapshot['image_path']}")
            item.setData(Qt.ItemDataRole.UserRole, str(snapshot["image_path"]))
            self._map_snapshots.addItem(item)
        if snapshots:
            self._map_snapshots.setCurrentRow(0)
        else:
            self._snapshot_view.set_snapshot(None)
            self._research_views.setCurrentWidget(self._research_map)
        media = self._service.project_media(self._project_id)
        self._project_media.setRowCount(len(media))
        for row_index, row in enumerate(media):
            for column, value in enumerate((row["media_type"], row["asset_public_id"], row["note"])):
                self._project_media.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _refresh_surveys(self) -> None:
        if not hasattr(self, "_survey_protocols") or not self._project_id:
            return
        protocols = self._service.survey_protocols(self._project_id)
        self._survey_protocol_ids = [str(row["protocol_id"]) for row in protocols]
        self._survey_protocols.setRowCount(len(protocols))
        for row_index, row in enumerate(protocols):
            values = (row["name"], row["version"], row["method"], row["target_group"],
                      f'{row["default_duration_minutes"]:g} min', f'{row["default_distance_m"]:g} m', "Yes" if row["active"] else "No")
            for column, value in enumerate(values): self._survey_protocols.setItem(row_index, column, QTableWidgetItem(str(value)))
        events = self._service.survey_events(self._project_id)
        self._survey_event_ids = [str(row["survey_event_id"]) for row in events]
        self._survey_events.setRowCount(len(events))
        for row_index, row in enumerate(events):
            values = (row["name"], f'{row["protocol_name"] or "Unspecified"} v{row["protocol_version"]}' if row["protocol_name"] else "Unspecified",
                      row["status"], row["start_text"] or "—", row["location_name"] or "—",
                      f'{row["sampling_unit_type"]}: {row["sampling_unit_name"] or "—"}',
                      f'{row["effort_duration_minutes"]:g} min', f'{row["effort_distance_m"]:g} m',
                      row["detected_count"], row["non_detection_count"])
            for column, value in enumerate(values): self._survey_events.setItem(row_index, column, QTableWidgetItem(str(value)))
        self._refresh_survey_detections()

    def _selected_survey_protocol_id(self) -> str | None:
        row = self._survey_protocols.currentRow()
        return self._survey_protocol_ids[row] if 0 <= row < len(self._survey_protocol_ids) else None

    def _selected_survey_event_id(self) -> str | None:
        row = self._survey_events.currentRow()
        return self._survey_event_ids[row] if 0 <= row < len(self._survey_event_ids) else None

    def _install_protocol_template(self) -> None:
        if not self._project_id: return
        templates = {
            "Mammal live-capture and release": dict(method="capture station", target_group="mammals", duration_minutes=60, distance_m=0, equipment=("species-appropriate traps", "scale", "calipers", "PPE", "release kit"), required_fields=("date", "time", "location", "observers", "species", "sex", "age class", "capture method", "release outcome", "body mass", "head-body length"), description="Document capture effort, handling, morphometrics, welfare observations and release outcome. Follow permits and animal-welfare approvals."),
            "Bird point count and biometrics": dict(method="point count / capture station", target_group="birds", duration_minutes=10, distance_m=100, equipment=("binoculars", "rangefinder", "audio recorder", "scale", "wing rule", "calipers"), required_fields=("date", "start time", "location", "observers", "weather", "effort", "species", "count", "detection method", "wing chord", "tarsus length", "body mass"), description="Standardised point-count effort with optional capture biometrics. Record non-detections and distinguish visual, acoustic and handled records."),
            "Marine animal survey and morphometrics": dict(method="vessel / shore transect", target_group="marine animals", duration_minutes=60, distance_m=1000, equipment=("GPS", "rangefinder", "camera", "depth sounder", "measuring board", "scale"), required_fields=("date", "time", "position", "platform", "observers", "sea state", "effort", "species", "count", "total length", "body mass", "observation depth"), description="Record effort-aware sightings, strandings or handled specimens. Include sea conditions, platform, distance, depth and animal morphometrics where permitted."),
        }
        label, ok = QInputDialog.getItem(self, "Protocol templates", "Install protocol", tuple(templates), 0, False)
        if not ok: return
        values = templates[label]
        existing = {str(row["name"]).casefold() for row in self._service.survey_protocols(self._project_id)}
        if label.casefold() in existing:
            QMessageBox.information(self, "Protocol templates", "That protocol is already installed for this project."); return
        try: self._service.create_survey_protocol(self._project_id, name=label, actor_id=self._actor_provider(), **values)
        except Exception as exc: QMessageBox.warning(self, "Protocol templates", str(exc)); return
        self._refresh_surveys()

    def _new_survey_protocol(self) -> None:
        if not self._project_id: return
        name, ok = QInputDialog.getText(self, "Survey protocol", "Protocol name")
        if not ok or not name.strip(): return
        method, ok = QInputDialog.getItem(self, "Survey protocol", "Method", ("point count", "transect", "quadrat", "station", "camera trap", "acoustic monitoring", "other"), 0, True)
        if not ok or not method.strip(): return
        target, ok = QInputDialog.getText(self, "Survey protocol", "Target species or group")
        if not ok: return
        description, ok = QInputDialog.getMultiLineText(self, "Survey protocol", "Instructions and method description")
        if not ok: return
        duration, ok = QInputDialog.getDouble(self, "Survey protocol", "Default duration (minutes)", 0, 0, 100000, 1)
        if not ok: return
        distance, ok = QInputDialog.getDouble(self, "Survey protocol", "Default distance (metres)", 0, 0, 10000000, 1)
        if not ok: return
        equipment, ok = QInputDialog.getText(self, "Survey protocol", "Equipment (comma separated)")
        if not ok: return
        required, ok = QInputDialog.getText(self, "Survey protocol", "Required fields (comma separated)", text="date,time,location,observers,effort")
        if not ok: return
        try:
            self._service.create_survey_protocol(self._project_id, name=name, method=method, target_group=target, description=description,
                duration_minutes=duration, distance_m=distance, equipment=tuple(x.strip() for x in equipment.split(",")),
                required_fields=tuple(x.strip() for x in required.split(",")), actor_id=self._actor_provider())
        except Exception as exc: QMessageBox.warning(self, "Survey protocol", str(exc)); return
        self._refresh_surveys()

    def _toggle_survey_protocol(self) -> None:
        protocol_id = self._selected_survey_protocol_id()
        if not protocol_id: return
        row = self._survey_protocols.currentRow(); active = self._survey_protocols.item(row, 6).text() != "Yes"
        self._service.set_survey_protocol_active(protocol_id, active, actor_id=self._actor_provider()); self._refresh_surveys()

    def _new_survey_event(self) -> None:
        if not self._project_id: return
        name, ok = QInputDialog.getText(self, "Survey event", "Event name")
        if not ok or not name.strip(): return
        protocols = self._service.survey_protocols(self._project_id, active_only=True)
        labels = ["No protocol"] + [f'{row["name"]} v{row["version"]}' for row in protocols]
        label, ok = QInputDialog.getItem(self, "Survey event", "Protocol", labels, 0, False)
        if not ok: return
        protocol_id = None if label == "No protocol" else str(protocols[labels.index(label)-1]["protocol_id"])
        start, ok = get_datetime_text(self, "Survey event", "Start date/time", value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        if not ok: return
        location, ok = QInputDialog.getText(self, "Survey event", "Location or station name")
        if not ok: return
        unit_type, ok = QInputDialog.getItem(self, "Survey event", "Sampling unit", ("station", "transect", "quadrat", "route", "deployment"), 0, False)
        if not ok: return
        unit_name, ok = QInputDialog.getText(self, "Survey event", "Sampling unit identifier")
        if not ok: return
        duration, ok = QInputDialog.getDouble(self, "Survey event", "Effort duration (minutes)", 0, 0, 100000, 1)
        if not ok: return
        distance, ok = QInputDialog.getDouble(self, "Survey event", "Effort distance (metres)", 0, 0, 10000000, 1)
        if not ok: return
        area, ok = QInputDialog.getDouble(self, "Survey event", "Effort area (square metres)", 0, 0, 1000000000, 1)
        if not ok: return
        coordinates, ok = QInputDialog.getText(self, "Survey event", "Latitude, longitude (optional)")
        if not ok: return
        latitude = longitude = None
        if coordinates.strip():
            try: latitude, longitude = (float(value.strip()) for value in coordinates.split(",", 1))
            except (TypeError, ValueError): QMessageBox.warning(self, "Survey event", "Enter coordinates as latitude, longitude."); return
        observers, ok = QInputDialog.getText(self, "Survey event", "Observers (comma separated)", text=self._actor_provider())
        if not ok: return
        habitat, ok = QInputDialog.getText(self, "Survey event", "Habitat")
        if not ok: return
        weather, ok = QInputDialog.getText(self, "Survey event", "Weather and conditions")
        if not ok: return
        equipment, ok = QInputDialog.getText(self, "Survey event", "Equipment (comma separated)")
        if not ok: return
        notes, ok = QInputDialog.getMultiLineText(self, "Survey event", "Field notes")
        if not ok: return
        try:
            self._service.create_survey_event(self._project_id, name=name, protocol_id=protocol_id, start_text=start,
                location_name=location, sampling_unit_type=unit_type, sampling_unit_name=unit_name,
                duration_minutes=duration, distance_m=distance, area_m2=area, latitude=latitude, longitude=longitude,
                observers=tuple(x.strip() for x in observers.split(",")), habitat=habitat,
                weather={"summary": weather.strip()} if weather.strip() else {},
                equipment=tuple(x.strip() for x in equipment.split(",")), notes=notes,
                actor_id=self._actor_provider())
        except Exception as exc: QMessageBox.warning(self, "Survey event", str(exc)); return
        self._refresh_surveys()

    def _new_survey_detection(self, detected: bool) -> None:
        event_id = self._selected_survey_event_id()
        if not event_id: QMessageBox.information(self, "Survey result", "Select a survey event first."); return
        taxon, ok = QInputDialog.getText(self, "Survey result", "Taxon or target name")
        if not ok or not taxon.strip(): return
        count = None
        if detected:
            value, ok = QInputDialog.getDouble(self, "Survey result", "Count", 1, 0, 100000000, 2)
            if not ok: return
            count = value
        try: self._service.add_survey_detection(event_id, taxon_name=taxon, detected=detected, count=count, actor_id=self._actor_provider())
        except Exception as exc: QMessageBox.warning(self, "Survey result", str(exc)); return
        self._refresh_surveys()

    def _refresh_survey_detections(self) -> None:
        if not hasattr(self, "_survey_detections"): return
        event_id = self._selected_survey_event_id(); rows = self._service.survey_detections(event_id) if event_id else ()
        self._survey_detections.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (row["taxon_name"], row["detection_state"].replace("_", " "), row["count_value"] if row["count_value"] is not None else "—", row["unit"], row["evidence_public_id"] or "—")
            for column, value in enumerate(values): self._survey_detections.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _research_area_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        feature = current.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(feature, dict):
            self._research_map.set_features((feature,))
            self._research_views.setCurrentWidget(self._research_map)

    def _show_all_research_areas(self) -> None:
        if not self._project_id:
            return
        areas = self._service.research_areas(self._project_id)
        self._research_map.set_features(tuple(area["feature"] for area in areas))
        self._research_views.setCurrentWidget(self._research_map)

    def _map_snapshot_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        self._snapshot_view.set_snapshot(current.data(Qt.ItemDataRole.UserRole))
        self._research_views.setCurrentWidget(self._snapshot_view)

    def _clear_research_drawing(self) -> None:
        self._research_map.clear_drawing()

    def _save_research_area(self) -> None:
        if not self._project_id:
            return
        name, accepted = QInputDialog.getText(self, "Save research area", "Area name")
        if not accepted:
            return
        try:
            self._service.save_research_area(
                self._project_id,
                name,
                self._research_map.coordinates(),
                actor_id=self._actor_provider(),
            )
            self._research_map.clear_drawing()
            self._refresh_research()
        except Exception as exc:
            QMessageBox.warning(self, "Research area", str(exc))

    def _import_research_area(self) -> None:
        if not self._project_id:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import research-area GeoJSON", "", "GeoJSON (*.geojson *.json)")
        if not path:
            return
        try:
            self._service.import_research_area(self._project_id, Path(path), actor_id=self._actor_provider())
            self._refresh_research()
        except Exception as exc:
            QMessageBox.warning(self, "Import research area", str(exc))

    def _export_research_area(self) -> None:
        item = self._research_areas.currentItem()
        if item is None:
            return
        feature = item.data(Qt.ItemDataRole.UserRole + 1)
        path, _ = QFileDialog.getSaveFileName(self, "Export research area", "research-area.geojson", "GeoJSON (*.geojson)")
        if path:
            Path(path).write_text(json.dumps(feature, indent=2, ensure_ascii=False), encoding="utf-8")

    def _delete_research_area(self) -> None:
        item = self._research_areas.currentItem()
        if item is None:
            return
        if QMessageBox.question(self, "Delete research area", "Delete this project research area?") != QMessageBox.StandardButton.Yes:
            return
        self._service.delete_research_area(str(item.data(Qt.ItemDataRole.UserRole)), actor_id=self._actor_provider())
        self._refresh_research()

    def _attach_selected_project_media(self) -> None:
        if not self._project_id:
            return
        asset_ids = tuple(dict.fromkeys(self._selected_asset_ids()))
        if not asset_ids:
            QMessageBox.information(self, "Attach project media", "Select images, sounds, videos or documents in a Library workspace first.")
            return
        types = {asset_id: "media" for asset_id in asset_ids}
        if self._library_database_path and self._library_database_path.is_file():
            with sqlite3.connect(self._library_database_path) as connection:
                for asset_id, media_type in connection.execute(
                    f"SELECT asset_public_id,asset_type FROM library_assets WHERE asset_public_id IN ({','.join('?' for _ in asset_ids)})",
                    asset_ids,
                ):
                    types[str(asset_id)] = str(media_type)
        self._service.attach_project_media(
            self._project_id,
            tuple((asset_id, types[asset_id]) for asset_id in asset_ids),
            actor_id=self._actor_provider(),
        )
        self._refresh_research()

    def _add_project_note(self) -> None:
        if not self._project_id:
            return
        title, accepted = QInputDialog.getText(self, "Project note", "Title")
        if not accepted:
            return
        body, accepted = QInputDialog.getMultiLineText(self, "Project note", "Note")
        if accepted:
            self._service.add_project_note(self._project_id, title, body, actor_id=self._actor_provider())

    def _export_research_package(self) -> None:
        if not self._project_id:
            QMessageBox.information(self, "Research package", "Select a project first.")
            return
        actor = str(self._actor_provider() or "local-user")
        project = next((row for row in self._service.accessible_projects(actor, permission="view") if row["project_id"] == self._project_id), None)
        if project is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export structured research package",
            f"{project['name']}-research-package.zip",
            "ZIP package (*.zip)",
        )
        if not path:
            return
        options = ProjectExportOptions(**{key: option.isChecked() for key, option in self._package_options.items()})
        try:
            self._service.export_research_package(
                self._project_id,
                Path(path),
                options=options,
                library_database=self._library_database_path,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Research package export failed", str(exc))
            return
        QMessageBox.information(self, "Research package created", f"Created structured project package:\n{path}")

    def _project_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        self._project_id = None if current is None else str(current.data(Qt.ItemDataRole.UserRole))
        self._task_id = None
        self.refresh_project()

    def select_project(self, project_id: str, *, research_area: bool = False) -> bool:
        """Select a project received from the V5 overview and preserve its context."""
        self.refresh()
        for row in range(self._projects.count()):
            item = self._projects.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == str(project_id):
                self._projects.setCurrentRow(row)
                if research_area:
                    self._tabs.setCurrentIndex(self._quality_tab_index + 1)
                return True
        return False

    def _new_project(self) -> None:
        name, accepted = QInputDialog.getText(self, "New project", "Project name")
        if not accepted or not name.strip():
            return
        owner, accepted = QInputDialog.getText(
            self, "Project owner", "Owner identity ID", text=self._actor_provider()
        )
        if not accepted:
            return
        due, accepted = get_datetime_text(self, "Project deadline", "Due date", include_time=False)
        if not accepted:
            return
        try:
            self._project_id = self._service.create_project(
                name, owner_id=owner.strip(), actor_id=self._actor_provider(), due_date=due.strip()
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "New project", str(exc))

    def _new_from_template(self) -> None:
        templates = self._service.templates()
        if not templates:
            QMessageBox.information(self, "Project templates", "No project templates exist yet.")
            return
        labels = tuple(str(row["name"]) for row in templates)
        label, accepted = QInputDialog.getItem(self, "New from template", "Template", labels, 0, False)
        if not accepted:
            return
        name, accepted = QInputDialog.getText(self, "New from template", "Project name")
        if not accepted or not name.strip():
            return
        template = templates[labels.index(label)]
        self._project_id = self._service.create_project(
            name, owner_id=self._actor_provider(), actor_id=self._actor_provider(),
            template_id=str(template["template_id"]),
        )
        self.refresh()

    def _delete_project(self) -> None:
        if not self._project_id:
            return
        if QMessageBox.question(
            self, "Delete project",
            "Delete this project and all tasks, comments, files, time, and audit activity?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_project(self._project_id, actor_id=self._actor_provider())
            self._project_id = None
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Delete project", str(exc))

    def _new_task(self, *, parent_id: str | None = None, milestone: bool = False) -> None:
        if not self._project_id:
            return
        dialog = TaskDialog(
            self._service.statuses(self._project_id),
            owners=self._service.project_members(self._project_id),
            phases=self._service.phases(self._project_id), sprints=self._service.sprints(self._project_id),
            current_user=self._actor_provider(),
            parent_task_id=parent_id, milestone=milestone, parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        title = str(values.pop("title"))
        try:
            self._task_id = self._service.create_task(
                self._project_id, title, actor_id=self._actor_provider(), **values
            )
            self.refresh_project()
        except Exception as exc:
            QMessageBox.warning(self, "New task", str(exc))

    def _edit_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        actor = self._actor_provider()
        editable = self._service.can_edit_task(task.task_id, actor)
        details = self._service.task_details(task.task_id)
        dialog = TaskDialog(
            self._service.statuses(self._project_id),
            owners=self._service.project_members(self._project_id),
            phases=self._service.phases(self._project_id), sprints=self._service.sprints(self._project_id),
            current_user=actor, task=task,
            description=str(details.get("description") or ""),
            read_only=not editable, parent=self,
        )
        result = dialog.exec()
        if not editable or result != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        values.pop("parent_task_id", None)
        try:
            self._service.update_task(task.task_id, actor_id=actor, **values)
            self.refresh_project()
        except Exception as exc:
            QMessageBox.warning(self, "Edit task", str(exc))

    def _save_task_note(self) -> None:
        if not self._task_id:
            QMessageBox.information(self, "Notes", "Select a task or subtask first.")
            return
        body = self._note_entry.toPlainText().strip()
        if not body:
            return
        try:
            self._service.add_task_note(self._task_id, body, author_id=self._actor_provider())
            self._note_entry.clear()
            self._refresh_task_details()
        except Exception as exc:
            QMessageBox.warning(self, "Notes", str(exc))

    def _new_subtask(self) -> None:
        if not self._task_id:
            QMessageBox.information(self, "New subtask", "Select the parent task first.")
            return
        self._new_task(parent_id=self._task_id)

    def _new_phase(self) -> None:
        if not self._project_id:
            return
        name, ok = QInputDialog.getText(self, "New phase", "Phase name")
        if not ok or not name.strip():
            return
        description, ok = QInputDialog.getMultiLineText(self, "New phase", "Description")
        if not ok:
            return
        budget, ok = QInputDialog.getDouble(self, "New phase", "Planned budget", 0, 0, 1_000_000_000, 2)
        if not ok:
            return
        try:
            self._service.create_phase(self._project_id, name, actor_id=self._actor_provider(), description=description, planned_budget=budget)
            self.refresh_project()
        except Exception as exc:
            QMessageBox.warning(self, "New phase", str(exc))

    def _assign_task_to_phase(self, task_id: str, phase_id: str) -> None:
        try:
            self._service.assign_task_phase(task_id, phase_id, actor_id=self._actor_provider())
            self._task_id = task_id; self.refresh_project()
        except Exception as exc:
            QMessageBox.warning(self, "Assign phase", str(exc))

    def _edit_phase(self, phase_id: str) -> None:
        phase = next((row for row in self._service.phases(self._project_id) if str(row['phase_id']) == phase_id), None)
        if phase is None:
            return
        name, ok = QInputDialog.getText(self, "Edit phase", "Phase name", text=str(phase['name']))
        if not ok or not name.strip():
            return
        planned, ok = QInputDialog.getDouble(self, "Edit phase", "Planned budget", float(phase['planned_budget']), 0, 1_000_000_000, 2)
        if not ok:
            return
        realized, ok = QInputDialog.getDouble(self, "Edit phase", "Realized budget", float(phase['realized_budget']), 0, 1_000_000_000, 2)
        if not ok:
            return
        try:
            self._service.update_phase(phase_id, actor_id=self._actor_provider(), name=name, planned_budget=planned, realized_budget=realized)
            self.refresh_project()
        except Exception as exc:
            QMessageBox.warning(self, "Edit phase", str(exc))

    def _hierarchy_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        kind = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or '')
        if kind == 'task':
            self._open_task(str(item.data(0, Qt.ItemDataRole.UserRole)), edit=True)
        elif kind == 'phase':
            phase_id = str(item.data(0, Qt.ItemDataRole.UserRole) or '')
            if phase_id:
                self._edit_phase(phase_id)

    def _new_milestone(self) -> None:
        self._new_task(milestone=True)

    def _selected_task(self) -> TaskSummary | None:
        return next((item for item in self._tasks if item.task_id == self._task_id), None)

    def _task_selected(self) -> None:
        items = self._task_tree.selectedItems()
        if not items:
            self._task_id = None
            self._refresh_task_details()
            return
        if str(items[0].data(0, Qt.ItemDataRole.UserRole + 1) or '') != 'task':
            self._task_id = None
        else:
            self._task_id = str(items[0].data(0, Qt.ItemDataRole.UserRole) or "") or None
        self._refresh_task_details()

    def _task_depth(self, task: TaskSummary) -> int:
        by_id = {item.task_id: item for item in self._tasks}
        depth = 0
        parent_id = task.parent_task_id
        visited: set[str] = set()
        while parent_id and parent_id in by_id and parent_id not in visited:
            visited.add(parent_id)
            depth += 1
            parent_id = by_id[parent_id].parent_task_id
        return depth

    def _refresh_task_table(self) -> None:
        """Render phases first, then the authoritative task/subtask hierarchy."""
        selected_id = self._task_id
        self._task_tree.clear()
        phases = self._service.phases(self._project_id) if self._project_id else ()
        by_id = {task.task_id: task for task in self._tasks}
        by_phase: dict[str | None, list[TaskSummary]] = {}
        for task in self._tasks:
            if task.parent_task_id is None:
                by_phase.setdefault(task.phase_id, []).append(task)
        children: dict[str, list[TaskSummary]] = {}
        for task in self._tasks:
            if task.parent_task_id:
                children.setdefault(task.parent_task_id, []).append(task)
        selected_item = None

        def add_task(parent_item: QTreeWidgetItem, task: TaskSummary) -> None:
            nonlocal selected_item
            parent = by_id.get(task.parent_task_id or '')
            item = QTreeWidgetItem((task.title, parent.title if parent else '', task.status_name, task.due_date))
            item.setData(0, Qt.ItemDataRole.UserRole, task.task_id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, 'task')
            parent_item.addChild(item)
            if task.task_id == selected_id: selected_item = item
            for child in children.get(task.task_id, ()): add_task(item, child)

        phase_ids = set()
        for phase in phases:
            phase_id = str(phase['phase_id']); phase_ids.add(phase_id)
            label = (f"▾ {phase['name']}  · Estimate {float(phase.get('calculated_estimate_hours',0)):g} h  "
                     f"· Realized {float(phase.get('calculated_realized_hours',0)):g} h  "
                     f"· Budget {float(phase.get('planned_budget',0)):g} / {float(phase.get('realized_budget',0)):g}")
            phase_item = QTreeWidgetItem((label, '', 'Phase', ''))
            phase_item.setData(0, Qt.ItemDataRole.UserRole, phase_id)
            phase_item.setData(0, Qt.ItemDataRole.UserRole + 1, 'phase')
            self._task_tree.addTopLevelItem(phase_item)
            for task in by_phase.get(phase_id, ()): add_task(phase_item, task)
        unassigned = QTreeWidgetItem(('Unassigned phase', '', 'Phase', ''))
        unassigned.setData(0, Qt.ItemDataRole.UserRole, '')
        unassigned.setData(0, Qt.ItemDataRole.UserRole + 1, 'phase')
        self._task_tree.addTopLevelItem(unassigned)
        for task in by_phase.get(None, ()): add_task(unassigned, task)
        for phase_id, tasks in by_phase.items():
            if phase_id is not None and phase_id not in phase_ids:
                for task in tasks: add_task(unassigned, task)
        self._task_tree.expandAll()
        for column in range(self._task_tree.columnCount()): self._task_tree.resizeColumnToContents(column)
        if selected_item is not None: self._task_tree.setCurrentItem(selected_item)

    def _refresh_task_details(self) -> None:
        self._checklist.blockSignals(True)
        self._checklist.clear()
        self._comments.clear()
        self._attachments.setRowCount(0)
        self._custom_values.setRowCount(0)
        self._subtasks.clear()
        self._evidence.setRowCount(0)
        self._time_entries.setRowCount(0)
        self._dependencies.setRowCount(0)
        self._notes.clear()
        self._activity_detail.clear()
        task = self._selected_task()
        if task is None:
            self._note_entry.clear()
            self._note_entry.setEnabled(False)
            self._save_note_button.setEnabled(False)
            self._task_header.setText("<h2>Select a task</h2><p>Choose a phase, task or subtask from the hierarchy.</p>")
            self._overview.setHtml("<p>No task selected.</p>")
            self._checklist.blockSignals(False)
            return

        editable = self._service.can_edit_task(task.task_id, self._actor_provider())
        self._note_entry.setEnabled(editable)
        self._save_note_button.setEnabled(editable)
        by_id = {item.task_id: item for item in self._tasks}
        parent = by_id.get(task.parent_task_id or "")
        parent_text = parent.title if parent else "Top-level task"
        kind = "Phase / milestone" if task.milestone else ("Subtask" if parent else "Task")
        self._task_header.setText(
            f"<h2>{task.title}</h2><p><b>{kind}</b> · Parent: {parent_text} · "
            f"Status: {task.status_name}</p>"
        )
        self._overview.setHtml(
            f"<h3>Overview</h3>"
            f"<p><b>Parent task</b>: {parent_text}</p>"
            f"<p><b>Owner</b>: {task.owner_id or 'Unassigned'}<br>"
            f"<b>Priority</b>: {task.priority}<br>"
            f"<b>Start</b>: {task.start_date or '—'}<br>"
            f"<b>Due</b>: {task.due_date or '—'}<br>"
            f"<b>Phase</b>: {task.phase_name or 'Unassigned'}<br>"
            f"<b>Sprint</b>: {task.sprint_name or 'Unscheduled'}<br>"
            f"<b>Manual estimate</b>: {task.manual_estimate_hours:g} hours<br>"
            f"<b>Calculated estimate</b>: {task.calculated_estimate_hours:g} hours<br>"
            f"<b>Effective estimate</b>: {task.effective_estimate_hours:g} hours<br>"
            f"<b>Realized</b>: {task.realized_hours:g} hours<br>"
            f"<b>Actual logged</b>: {task.actual_hours:g} hours<br>"
            f"<b>Progress</b>: {task.progress}%</p>"
        )

        for child in (item for item in self._tasks if item.parent_task_id == task.task_id):
            row = QTreeWidgetItem((child.title, task.title, child.status_name, child.owner_id, child.due_date))
            row.setData(0, Qt.ItemDataRole.UserRole, child.task_id)
            self._subtasks.addTopLevelItem(row)

        for row in self._service.checklist(self._task_id):
            item = QListWidgetItem(str(row["title"]))
            item.setData(Qt.ItemDataRole.UserRole, str(row["item_id"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if row["completed"] else Qt.CheckState.Unchecked)
            self._checklist.addItem(item)
        self._checklist.blockSignals(False)

        comments = self._service.comments(self._task_id)
        self._comments.setHtml(
            "".join(
                f"<p><b>{row['author_id']}</b> · {self._format_time(row['created_at_us'])}<br>"
                f"{str(row['body']).replace(chr(10), '<br>')}</p>"
                for row in comments
            ) or "<p>No discussions yet.</p>"
        )

        attachments = self._service.attachments(self._task_id)
        self._attachments.setRowCount(len(attachments))
        for r, row in enumerate(attachments):
            for c, key in enumerate(("name", "kind", "version", "location")):
                item = QTableWidgetItem(str(row[key]))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(row["attachment_id"]))
                self._attachments.setItem(r, c, item)

        time_rows = self._service.time_entries(self._task_id)
        self._time_entries.setRowCount(len(time_rows))
        for r, row in enumerate(time_rows):
            values = (
                self._format_time(row["created_at_us"]),
                row["user_id"],
                f"{float(row['minutes']) / 60.0:g}",
                row["note"],
                row["entry_id"],
            )
            for c, value in enumerate(values):
                self._time_entries.setItem(r, c, QTableWidgetItem(str(value)))

        dependencies = self._service.dependencies(self._task_id)
        self._dependencies.setRowCount(len(dependencies))
        for r, row in enumerate(dependencies):
            for c, key in enumerate(("title", "status", "dependency_type")):
                self._dependencies.setItem(r, c, QTableWidgetItem(str(row[key])))

        notes = self._service.task_notes(self._task_id)
        self._notes.setHtml(
            "".join(
                f"<p><b>{row['author_id']}</b> · {self._format_time(row['created_at_us'])}<br>"
                f"{str(row['body']).replace(chr(10), '<br>')}</p>"
                for row in notes
            ) or "<p>No notes yet.</p>"
        )

        activity = self._service.task_activity(self._task_id)
        self._activity_detail.setHtml(
            "".join(
                f"<p><b>{row['event_type']}</b> · {row['actor_id']} · "
                f"{self._format_time(row['created_at_us'])}<br>{row['details_json']}</p>"
                for row in activity
            ) or "<p>No task activity yet.</p>"
        )

        custom_values = self._service.custom_field_values(self._task_id)
        self._custom_values.setRowCount(len(custom_values))
        for r, row in enumerate(custom_values):
            value = str(row["value_json"])
            if value == "null":
                value = ""
            for c, text in enumerate((row["name"], row["field_type"], value)):
                item = QTableWidgetItem(str(text))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(row["field_id"]))
                self._custom_values.setItem(r, c, item)

    def _set_custom_value(self) -> None:
        if not self._task_id:
            return
        rows = self._custom_values.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Custom field", "Select a custom field first.")
            return
        field = self._custom_values.item(rows[0].row(), 0)
        current = self._custom_values.item(rows[0].row(), 2)
        value, accepted = QInputDialog.getText(
            self, "Custom field", "Value", text="" if current is None else current.text()
        )
        if accepted and field is not None:
            self._service.set_custom_field_value(
                self._task_id, str(field.data(Qt.ItemDataRole.UserRole)), value,
                actor_id=self._actor_provider(),
            )
            self._refresh_task_details()

    def _change_status(self) -> None:
        if not self._task_id or not self._project_id:
            return
        statuses = self._service.statuses(self._project_id)
        labels = tuple(str(row["name"]) for row in statuses)
        label, accepted = QInputDialog.getItem(self, "Change task status", "Status", labels, 0, False)
        if accepted:
            try:
                self._service.update_task(
                    self._task_id, actor_id=self._actor_provider(),
                    status_id=str(statuses[labels.index(label)]["status_id"]),
                    progress=100 if str(statuses[labels.index(label)]["category"]) == "done" else 0,
                )
                self.refresh_project()
            except Exception as exc:
                QMessageBox.warning(self, "Change status", str(exc))

    def _assign_owner(self) -> None:
        if not self._task_id:
            return
        owner, accepted = QInputDialog.getText(self, "Assign task", "Owner identity ID")
        if accepted:
            self._service.update_task(
                self._task_id, actor_id=self._actor_provider(), owner_id=owner.strip()
            )
            self.refresh_project()

    def _set_dependency(self) -> None:
        if not self._task_id:
            return
        candidates = tuple(item for item in self._tasks if item.task_id != self._task_id)
        labels = tuple(f"{item.title} [{item.task_id[:8]}]" for item in candidates)
        if not labels:
            return
        label, accepted = QInputDialog.getItem(self, "Task dependency", "Cannot start until", labels, 0, False)
        if accepted:
            try:
                self._service.add_dependency(
                    self._task_id, candidates[labels.index(label)].task_id,
                    actor_id=self._actor_provider(),
                )
                self.refresh_project()
            except Exception as exc:
                QMessageBox.warning(self, "Task dependency", str(exc))

    def _delete_task(self) -> None:
        if self._task_id:
            try:
                self._service.delete_task(self._task_id, actor_id=self._actor_provider())
                self._task_id = None
                self.refresh_project()
            except Exception as exc:
                QMessageBox.warning(self, "Delete task", str(exc))

    def _add_checklist(self) -> None:
        if not self._task_id:
            return
        title, accepted = QInputDialog.getText(self, "Checklist item", "Action")
        if accepted and title.strip():
            self._service.add_checklist_item(
                self._task_id, title, actor_id=self._actor_provider()
            )
            self._refresh_task_details()

    def _checklist_changed(self, item: QListWidgetItem) -> None:
        self._service.set_checklist_completed(
            str(item.data(Qt.ItemDataRole.UserRole)),
            item.checkState() == Qt.CheckState.Checked,
            actor_id=self._actor_provider(),
        )

    def _add_comment(self) -> None:
        if not self._task_id:
            return
        body, accepted = QInputDialog.getMultiLineText(
            self, "Task comment", "Comment; use @identity-id to notify a user"
        )
        if accepted and body.strip():
            try:
                self._service.add_comment(
                    self._task_id, body, author_id=self._actor_provider()
                )
                self._refresh_task_details()
                self._refresh_activity()
            except Exception as exc:
                QMessageBox.warning(self, "Task comment", str(exc))

    def _attach_file(self) -> None:
        if not self._task_id:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Attach task file")
        if path:
            self._service.add_attachment(
                self._task_id, Path(path).name, path, actor_id=self._actor_provider()
            )
            self._refresh_task_details()

    def _attach_link(self) -> None:
        if not self._task_id:
            return
        url, accepted = QInputDialog.getText(self, "External link", "URL")
        if accepted and url.strip():
            name, accepted = QInputDialog.getText(self, "External link", "Display name", text=url)
            if accepted:
                self._service.add_attachment(
                    self._task_id, name, url, kind="link", actor_id=self._actor_provider()
                )
                self._refresh_task_details()

    def _attach_version(self) -> None:
        if not self._task_id:
            return
        rows = self._attachments.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Document version", "Select the previous attachment.")
            return
        previous = self._attachments.item(rows[0].row(), 0)
        path, _ = QFileDialog.getOpenFileName(self, "New document version")
        if previous is not None and path:
            self._service.add_attachment(
                self._task_id, Path(path).name, path, actor_id=self._actor_provider(),
                previous_attachment_id=str(previous.data(Qt.ItemDataRole.UserRole)),
            )
            self._refresh_task_details()

    def _refresh_kanban(self) -> None:
        while self._kanban_layout.count():
            item = self._kanban_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not self._project_id:
            return
        actor = self._actor_provider()
        editable = self._service.can(self._project_id, actor, "edit")
        tasks_by_id = {task.task_id: task for task in self._tasks}

        def depth(task: TaskSummary) -> int:
            seen: set[str] = set()
            current = task
            level = 0
            while current.parent_task_id and current.parent_task_id not in seen:
                seen.add(current.parent_task_id)
                parent = tasks_by_id.get(current.parent_task_id)
                if parent is None:
                    break
                level += 1
                current = parent
            return level

        for status in self._service.statuses(self._project_id):
            column = QFrame()
            column.setFrameShape(QFrame.Shape.StyledPanel)
            column.setMinimumWidth(250)
            column.setMaximumWidth(340)
            layout = QVBoxLayout(column)
            count = sum(task.status_id == status["status_id"] for task in self._tasks)
            limit = "" if status["wip_limit"] is None else f" / {status['wip_limit']}"
            heading = QLabel(f"<b>{status['name']}</b> · {count}{limit}")
            heading.setStyleSheet(f"border-left: 5px solid {status['color']}; padding-left: 6px")
            layout.addWidget(heading)
            task_list = KanbanTaskList(str(status["status_id"]), editable=editable, parent=column)
            task_list.setToolTip(
                "Drag tasks or subtasks to another column to update their status."
                if editable else "You have read-only access to this project."
            )
            task_list.task_dropped.connect(self._move_kanban_task)
            task_list.itemDoubleClicked.connect(
                lambda item, _column: self._open_task(str(item.data(Qt.ItemDataRole.UserRole)), edit=True)
            )
            for task in self._tasks:
                if task.status_id != status["status_id"]:
                    continue
                indent = "    " * depth(task)
                prefix = "↳ " if task.parent_task_id else ""
                parent = next((candidate for candidate in self._tasks if candidate.task_id == task.parent_task_id), None)
                parent_line = f"{indent}   Parent: {parent.title}\n" if parent else ""
                item = QListWidgetItem(
                    f"{indent}{prefix}{'⚠ ' if task.blocked else ''}{task.title}\n"
                    f"{parent_line}{indent}   {task.owner_id or 'Unassigned'} · {task.priority} · "
                    f"{task.due_date or 'No deadline'}"
                )
                item.setData(Qt.ItemDataRole.UserRole, task.task_id)
                item.setToolTip("Drag to change status; double-click to open the task.")
                task_list.addItem(item)
            layout.addWidget(task_list, 1)
            self._kanban_layout.addWidget(column)
        self._kanban_layout.addStretch(1)

    def _move_kanban_task(self, task_id: str, status_id: str) -> None:
        """Persist a Kanban drop and refresh every synchronized task view."""
        task = next((row for row in self._tasks if row.task_id == task_id), None)
        if task is None or task.status_id == status_id:
            return
        try:
            self._service.update_task(
                task_id, actor_id=self._actor_provider(), status_id=status_id
            )
        except (KeyError, PermissionError, ValueError) as error:
            QMessageBox.warning(self, "Move task", str(error))
            self._refresh_kanban()
            return
        self.refresh_project()

    def _open_task(self, task_id: str, *, edit: bool = False) -> None:
        self._tabs.setCurrentIndex(0)
        iterator = QTreeWidgetItemIterator(self._task_tree)
        while iterator.value():
            item = iterator.value()
            if str(item.data(0, Qt.ItemDataRole.UserRole) or "") == task_id:
                self._task_tree.setCurrentItem(item)
                self._task_tree.scrollToItem(item)
                self._task_id = task_id
                self._refresh_task_details()
                if edit:
                    self._edit_task()
                return
            iterator += 1

    def _refresh_grid(self) -> None:
        self._grid.setRowCount(len(self._tasks))
        for row, task in enumerate(self._tasks):
            values = (
                task.task_id, task.title, task.parent_task_id or "", task.phase_name, task.sprint_name,
                task.owner_id, task.status_name, task.priority, task.start_date, task.due_date,
                task.manual_estimate_hours, task.calculated_estimate_hours,
                task.effective_estimate_hours, task.realized_hours, task.actual_hours,
                task.progress, task.blocked,
            )
            for column, value in enumerate(values):
                self._grid.setItem(row, column, QTableWidgetItem(str(value)))

    def _refresh_calendar(self) -> None:
        scope = str(self._calendar_scope.currentData() or "mine")
        actor = self._actor_provider()
        visible_tasks = [task for task in self._tasks if scope == "project" or task.owner_id == actor]
        counts: dict[str, int] = {}
        for task in visible_tasks:
            for day in {task.start_date, task.due_date}:
                if day:
                    counts[day] = counts.get(day, 0) + 1
        self._calendar.set_activity_counts(counts)
        self._calendar_items.clear()
        selected = self._calendar.selectedDate().toString("yyyy-MM-dd")
        for task in visible_tasks:
            if task.due_date == selected or task.start_date == selected:
                marker = "Milestone" if task.milestone else "Task"
                self._calendar_items.addItem(
                    f"{marker}: {task.title} · {task.status_name} · {task.owner_id or 'Unassigned'}"
                )
        for holiday in self._service.public_holidays(selected, selected):
            self._calendar_items.addItem(f"Public holiday: {holiday['name']}")

    def _add_public_holiday(self) -> None:
        selected = self._calendar.selectedDate().toString("yyyy-MM-dd")
        name, accepted = QInputDialog.getText(
            self, "Public holiday", f"Holiday name for {selected}"
        )
        if accepted and name.strip():
            self._service.add_public_holiday(selected, name)
            self._refresh_calendar()

    def _refresh_workload(self) -> None:
        if not self._project_id:
            return
        rows = self._service.workload(self._project_id)
        self._workload.setRowCount(len(rows))
        for r, row in enumerate(rows):
            open_hours = float(row["open_estimate_hours"]); actual = float(row["actual_hours"])
            values = (row["user_id"],row["role"],f"{row['scheduled_hours']:g} h",f"{row['absence_hours']:g} h",
                      f"{row['organisational_hours']:g} h",f"{row['allocated_hours']:g} h",f"{row['remaining_hours']:g} h",
                      row["task_count"],f"{open_hours:g} h",f"{actual:g} h")
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 6 and float(row["remaining_hours"]) < 0:
                    item.setForeground(QColor("#ef4444"))
                self._workload.setItem(r, c, item)

    def _log_time(self) -> None:
        if not self._task_id:
            QMessageBox.information(self, "Log time", "Select a task in the Tasks view first.")
            return
        minutes, accepted = QInputDialog.getInt(self, "Log time", "Minutes", 30, 1, 1_000_000)
        if accepted:
            note, accepted = QInputDialog.getText(self, "Log time", "Note")
            if accepted:
                self._service.log_time(self._task_id, self._actor_provider(), minutes, note=note)
                self.refresh_project()

    def _refresh_dashboard(self) -> None:
        if not self._project_id:
            return
        values = self._service.dashboard(self._project_id)
        self._dashboard_cards.setText(
            f"<h2>{values['completion_percent']}% complete</h2>"
            f"<p><b>{values['total']}</b> tasks · <b>{values['overdue']}</b> overdue · "
            f"<b>{values['blocked']}</b> blocked · <b>{values['actual_hours']:.1f}</b> / "
            f"<b>{values['estimated_hours']:.1f}</b> hours</p>"
        )
        metrics = [
            ("Total tasks", values["total"]), ("Completed", values["done"]),
            ("Overdue", values["overdue"]), ("Blocked", values["blocked"]),
            ("Estimated hours", values["estimated_hours"]),
            ("Actual hours", values["actual_hours"]),
        ] + [(f"Status · {name}", count) for name, count in values["by_status"].items()]
        self._dashboard_table.setRowCount(len(metrics))
        for r, (name, value) in enumerate(metrics):
            self._dashboard_table.setItem(r, 0, QTableWidgetItem(str(name)))
            self._dashboard_table.setItem(r, 1, QTableWidgetItem(str(value)))
        agile = self._service.agile_metrics(self._project_id)
        self._agile.setPlainText(
            "Velocity by sprint\n"
            + "\n".join(
                f"{sprint}: {row['done']:.1f} done / {row['planned']:.1f} planned"
                for sprint, row in agile["sprints"].items()
            )
            + "\n\nCumulative flow\n"
            + "\n".join(f"{name}: {count}" for name, count in agile["cumulative_flow"].items())
        )

    def _refresh_activity(self) -> None:
        if not self._project_id:
            return
        rows = self._service.activity(self._project_id)
        self._activity.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = (
                self._format_time(row["created_at_us"]), row["actor_id"], row["event_type"],
                row["task_id"] or "", row["details_json"],
            )
            for c, value in enumerate(values):
                self._activity.setItem(r, c, QTableWidgetItem(str(value)))
        notifications = self._service.notifications(self._actor_provider())
        self._notifications.clear()
        for row in notifications:
            self._notifications.addItem(str(row["message"]))

    def _refresh_admin(self) -> None:
        if not self._project_id:
            return
        statuses = self._service.statuses(self._project_id)
        self._statuses.setRowCount(len(statuses))
        for r, row in enumerate(statuses):
            for c, key in enumerate(("name", "category", "color", "display_order", "wip_limit")):
                self._statuses.setItem(r, c, QTableWidgetItem(str(row[key] or "")))
        with self._service._connect() as connection:
            members = connection.execute(
                "SELECT user_id,role FROM pm_project_members WHERE project_id=? ORDER BY user_id",
                (self._project_id,),
            ).fetchall()
        self._members.setRowCount(len(members))
        for r, row in enumerate(members):
            self._members.setItem(r, 0, QTableWidgetItem(str(row[0])))
            self._members.setItem(r, 1, QTableWidgetItem(str(row[1])))

    def _add_status(self) -> None:
        if not self._project_id:
            return
        name, accepted = QInputDialog.getText(self, "Custom status", "Name")
        if not accepted or not name.strip():
            return
        category, accepted = QInputDialog.getItem(
            self, "Custom status", "Category", ("todo", "active", "review", "blocked", "done"), 0, False
        )
        if accepted:
            self._service.add_status(
                self._project_id, name, category, "#64748b", actor_id=self._actor_provider()
            )
            self.refresh_project()

    def _set_member_role(self) -> None:
        if not self._project_id:
            return
        user, accepted = QInputDialog.getText(self, "Project member", "User identity ID")
        if not accepted or not user.strip():
            return
        role, accepted = QInputDialog.getItem(
            self, "Project member", "Role", tuple(ROLE_PERMISSIONS), 0, False
        )
        if accepted:
            self._service.set_member_role(
                self._project_id, user, role, actor_id=self._actor_provider()
            )
            self._refresh_admin()
            self._context.permissions_changed(self._project_id, source="project-management")

    def _add_custom_field(self) -> None:
        if not self._project_id:
            return
        name, accepted = QInputDialog.getText(self, "Custom task field", "Field name")
        if not accepted or not name.strip():
            return
        field_type, accepted = QInputDialog.getItem(
            self, "Custom task field", "Type", ("text", "number", "date", "boolean", "choice"), 0, False
        )
        if accepted:
            self._service.add_custom_field(
                self._project_id, name, field_type, actor_id=self._actor_provider()
            )
            self._refresh_admin()
            self._refresh_task_details()

    def _save_template(self) -> None:
        if not self._project_id:
            return
        name, accepted = QInputDialog.getText(self, "Project template", "Template name")
        if accepted and name.strip():
            self._service.save_template(self._project_id, name, actor_id=self._actor_provider())

    def _preview_portal(self) -> None:
        if not self._project_id:
            return
        snapshot = self._service.client_portal_snapshot(self._project_id)
        viewer = QMessageBox(self)
        viewer.setWindowTitle("Restricted client portal preview")
        viewer.setText(
            f"<h2>{snapshot['project']['name']}</h2>"
            f"<p>Status: {snapshot['project']['status']} · due {snapshot['project']['due_date']}</p>"
            f"<p>{snapshot['health']['completion_percent']}% complete · "
            f"{snapshot['health']['overdue']} overdue</p>"
            f"<p>Only high-level project health and milestones are exposed. "
            f"Internal comments, activity, files, capacity, and time entries are excluded.</p>"
        )
        viewer.exec()

    def _materialize_recurring(self) -> None:
        if self._project_id:
            count = self._service.materialize_recurring_tasks(
                self._project_id, actor_id=self._actor_provider()
            )
            QMessageBox.information(self, "Recurring tasks", f"Created {count} due task(s).")
            self.refresh_project()

    def _export_csv(self) -> None:
        if not self._project_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export project tasks", "project-tasks.csv", "CSV (*.csv)")
        if path:
            self._service.export_csv(self._project_id, Path(path))

    def _export_excel(self) -> None:
        if not self._project_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export project tasks", "project-tasks.xlsx", "Excel workbook (*.xlsx)"
        )
        if path:
            self._service.export_xlsx(self._project_id, Path(path))

    def _export_pdf(self) -> None:
        if not self._project_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export project report", "project-report.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        document = QTextDocument()
        document.setHtml(self._service.report_html(self._project_id))
        document.print_(printer)

    @staticmethod
    def _format_time(value: object) -> str:
        try:
            return datetime.fromtimestamp(int(value) / 1_000_000).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OSError):
            return str(value)
