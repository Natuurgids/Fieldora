"""Integrated, offline help and shortcut discovery for Fieldora."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


@dataclass(frozen=True, slots=True)
class HelpTopic:
    topic_id: str
    title: str
    relative_path: str
    workspace: str | None = None
    section: str = "Using Fieldora"


HELP_TOPICS = (
    HelpTopic(
        "quick-start", "Quick Start", "getting-started/quick-start.md", "Library", "Getting Started"
    ),
    HelpTopic("user-guide", "User Guide", "user-guide/README.md", "Library", "Getting Started"),
    HelpTopic(
        "import",
        "Importing and Exporting",
        "user-guide/import-export.md",
        "Imports",
        "Using Fieldora",
    ),
    HelpTopic(
        "ai-review",
        "AI and Regional Resources",
        "user-guide/ai-and-resources.md",
        "AI Review",
        "Using Fieldora",
    ),
    HelpTopic(
        "observation-workflow", "Unified Observation Workflow",
        "user-guide/unified-observation-workflow.md", "Observations Overview", "Using Fieldora"
    ),
    HelpTopic(
        "offline-maps",
        "Offline Maps",
        "user-guide/offline-maps.md",
        "Offline Maps",
        "Using Fieldora",
    ),
    HelpTopic(
        "marine-maritime",
        "Marine Science and Maritime Operations",
        "user-guide/marine-maritime.md",
        "Marine & Freshwater Science",
        "Using Fieldora",
    ),
    HelpTopic(
        "home-calendar",
        "Home and Research Calendar",
        "user-guide/home-and-calendar.md",
        "Home",
        "Using Fieldora",
    ),
    HelpTopic(
        "background-thumbnails",
        "Background Thumbnails",
        "user-guide/background-thumbnails.md",
        "Photos",
        "Using Fieldora",
    ),
    HelpTopic(
        "research-calendar",
        "Research Calendar",
        "user-guide/home-and-calendar.md",
        "Science Calendar",
        "Using Fieldora",
    ),
    HelpTopic(
        "maritime-operations",
        "Maritime Operations",
        "user-guide/marine-maritime.md",
        "Maritime Operations",
        "Using Fieldora",
    ),
    HelpTopic(
        "taxonomy",
        "Taxonomy Library",
        "user-guide/taxonomy-library.md",
        "Taxonomy",
        "Using Fieldora",
    ),
    HelpTopic(
        "backup-recovery",
        "Backup and Recovery",
        "operations/backup-recovery.md",
        "Health Check",
        "Operations",
    ),
    HelpTopic(
        "maintenance-center",
        "Maintenance Center",
        "operations/maintenance-center.md",
        "Settings",
        "Operations",
    ),
    HelpTopic(
        "updates", "Offline Updates", "operations/offline-updates.md", "Updates", "Operations"
    ),
    HelpTopic(
        "health", "Health Center", "operations/health-center.md", "Health Check", "Operations"
    ),
    HelpTopic(
        "troubleshooting",
        "Troubleshooting",
        "operations/troubleshooting.md",
        "Diagnostics",
        "Reference",
    ),
    HelpTopic(
        "keyboard",
        "Keyboard Shortcuts",
        "accessibility/ACCESSIBILITY_AND_KEYBOARD.md",
        None,
        "Reference",
    ),
    HelpTopic("vision", "Vision", "VISION.md", None, "Project"),
    HelpTopic("philosophy", "Development Philosophy", "PHILOSOPHY.md", None, "Project"),
    HelpTopic("release-notes", "What's New and Release Notes", "RELEASE_NOTES.md", None, "Project"),
    HelpTopic("roadmap", "Roadmap and Future Releases", "user-guide/roadmap.md", None, "Project"),
    HelpTopic("architecture", "Architecture", "ARCHITECTURE.md", None, "Developer Documentation"),
    HelpTopic(
        "adrs",
        "Architecture Decisions",
        "ARCHITECTURE_DECISIONS.md",
        None,
        "Developer Documentation",
    ),
    HelpTopic("database", "Database", "DATABASE.md", None, "Developer Documentation"),
    HelpTopic("ai-architecture", "AI Architecture", "AI.md", None, "Developer Documentation"),
    HelpTopic("gui-architecture", "GUI Architecture", "GUI.md", None, "Developer Documentation"),
    HelpTopic(
        "coding-standard", "Coding Standard", "CODING_STANDARD.md", None, "Developer Documentation"
    ),
    HelpTopic(
        "plugin-api", "Plugin and Extension API", "PLUGIN_API.md", None, "Developer Documentation"
    ),
    HelpTopic(
        "project-spec", "Project Specification", "PROJECT_SPEC.md", None, "Developer Documentation"
    ),
    HelpTopic(
        "version2-charter",
        "Version 2 Development Charter",
        "VERSION2_DEVELOPMENT_CHARTER.md",
        None,
        "Developer Documentation",
    ),
    HelpTopic(
        "handover",
        "Version 1 Project Handover",
        "PROJECT_HANDOVER.md",
        None,
        "Developer Documentation",
    ),
    HelpTopic(
        "build-windows-installer",
        "Build Windows Installer",
        "developer/build-windows-installer.md",
        None,
        "Developer Documentation",
    ),
)
WORKSPACE_TOPIC = {topic.workspace: topic.topic_id for topic in HELP_TOPICS if topic.workspace}
WORKSPACE_TOPIC.update(
    {
        "Home": "home-calendar",
        "Library Overview": "import",
        "Observations Overview": "observation-workflow",
        "Research Overview": "home-calendar",
        "Knowledge & AI Overview": "ai-review",
        "Administration Overview": "maintenance-center",
        "Help & Guides": "user-guide",
    }
)


def documentation_root() -> Path:
    """Resolve bundled docs in source and installed-release layouts."""
    package_help = Path(__file__).resolve().parents[2] / "resources" / "help"
    candidates = (
        package_help,
        Path(__file__).resolve().parents[4] / "docs",
        Path(__file__).resolve().parents[3] / "docs",
        Path.cwd() / "docs",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def topic_by_id(topic_id: str) -> HelpTopic:
    for topic in HELP_TOPICS:
        if topic.topic_id == topic_id:
            return topic
    raise KeyError(topic_id)


def topic_text(topic: HelpTopic) -> str:
    path = (documentation_root() / topic.relative_path).resolve()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"# {topic.title}\n\nThis help topic is unavailable in the current installation.\n\nExpected file: `{path}`"


class HelpBrowserDialog(QDialog):
    """Searchable browser for documentation shipped with Fieldora."""

    def __init__(
        self, parent: QWidget | None = None, *, initial_topic: str = "quick-start"
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fieldora Help")
        self.resize(980, 680)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search help topics")
        self._search.setAccessibleName("Search Fieldora help")
        self._topics = QListWidget(self)
        self._topics.setAccessibleName("Help topics")
        self._browser = QTextBrowser(self)
        self._browser.setAccessibleName("Help article")
        self._browser.setOpenExternalLinks(False)
        current_section = None
        for topic in HELP_TOPICS:
            if topic.section != current_section:
                current_section = topic.section
                header = QListWidgetItem(current_section)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                self._topics.addItem(header)
            item = QListWidgetItem(topic.title)
            item.setData(Qt.ItemDataRole.UserRole, topic.topic_id)
            self._topics.addItem(item)
        self._search.textChanged.connect(self._filter)
        self._topics.currentItemChanged.connect(self._show_current)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        left = QVBoxLayout()
        left.addWidget(QLabel("Contents"))
        left.addWidget(self._search)
        left.addWidget(self._topics, 1)
        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addWidget(self._browser, 3)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self.open_topic(initial_topic)

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self._topics.count()):
            item = self._topics.item(row)
            topic_id = item.data(Qt.ItemDataRole.UserRole)
            if topic_id is None:
                item.setHidden(False)
                continue
            topic = topic_by_id(str(topic_id))
            haystack = f"{topic.title}\n{topic_text(topic)}".casefold()
            item.setHidden(bool(needle) and needle not in haystack)

    def _show_current(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        topic_id = current.data(Qt.ItemDataRole.UserRole)
        if topic_id is None:
            return
        topic = topic_by_id(str(topic_id))
        self._browser.setMarkdown(topic_text(topic))

    def open_topic(self, topic_id: str) -> None:
        for row in range(self._topics.count()):
            item = self._topics.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == topic_id:
                item.setHidden(False)
                self._topics.setCurrentItem(item)
                return
        self._topics.setCurrentRow(0)
