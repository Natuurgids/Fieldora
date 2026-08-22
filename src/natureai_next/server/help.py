"""Safe, packaged help catalogue for the Fieldora server web client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServerHelpTopic:
    topic_id: str
    title: str
    relative_path: str
    workspace: str


SERVER_HELP_TOPICS = (
    ServerHelpTopic("quick-start", "Quick start", "getting-started/quick-start.md", "home"),
    ServerHelpTopic("library", "Library, import and export", "user-guide/import-export.md", "library"),
    ServerHelpTopic("observations", "Observations and evidence", "user-guide/unified-observation-workflow.md", "observations"),
    ServerHelpTopic("research", "Projects, maps and research", "user-guide/home-and-calendar.md", "research"),
    ServerHelpTopic("knowledge", "AI identification and review", "user-guide/ai-and-resources.md", "knowledge"),
    ServerHelpTopic("offline-maps", "Offline maps", "user-guide/offline-maps.md", "research"),
    ServerHelpTopic("taxonomy", "Taxonomy and GBIF", "user-guide/taxonomy-library.md", "knowledge"),
    ServerHelpTopic("backup-recovery", "Backup and recovery", "operations/backup-recovery.md", "administration"),
    ServerHelpTopic("health", "Health and diagnostics", "operations/health-center.md", "administration"),
    ServerHelpTopic("troubleshooting", "Troubleshooting", "operations/troubleshooting.md", "administration"),
    ServerHelpTopic("accessibility", "Keyboard and accessibility", "accessibility/ACCESSIBILITY_AND_KEYBOARD.md", "help"),
    ServerHelpTopic("server", "Server administration", "SERVER_ARCHITECTURE.md", "administration"),
    ServerHelpTopic("staged-ingestion", "Staged ingestion", "STAGED_INGESTION.md", "library"),
    ServerHelpTopic("release-notes", "What's new", "RELEASE_NOTES.md", "help"),
)


def help_root() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "help"


def help_catalogue() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "topic_id": topic.topic_id,
            "title": topic.title,
            "workspace": topic.workspace,
        }
        for topic in SERVER_HELP_TOPICS
    )


def help_topic(topic_id: str) -> dict[str, str] | None:
    topic = next((item for item in SERVER_HELP_TOPICS if item.topic_id == topic_id), None)
    if topic is None:
        return None
    path = help_root() / topic.relative_path
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = f"# {topic.title}\n\nThis packaged guide is unavailable."
    return {
        "topic_id": topic.topic_id,
        "title": topic.title,
        "workspace": topic.workspace,
        "content": content,
    }
