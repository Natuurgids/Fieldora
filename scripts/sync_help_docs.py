"""Synchronize canonical authoring documentation into packaged runtime help."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / "src" / "natureai_next" / "resources" / "help"

ROOT_TOPICS = (
    "AI.md",
    "ARCHITECTURE.md",
    "ARCHITECTURE_DECISIONS.md",
    "BACKLOG.md",
    "CHANGELOG.md",
    "CODING_STANDARD.md",
    "CONFIGURATION.md",
    "DATABASE.md",
    "GUI.md",
    "INSTALLATION.md",
    "NAVIGATION.md",
    "PHILOSOPHY.md",
    "PLUGIN_API.md",
    "PROJECT_MANAGEMENT.md",
    "PROJECT_SPEC.md",
    "QUICKSTART_WINDOWS.md",
    "RELEASE_NOTES.md",
    "ROADMAP.md",
    "STAGED_INGESTION.md",
    "VALIDATION.md",
    "VERSION2_DEVELOPMENT_CHARTER.md",
    "VISION.md",
)

DOC_TREES = (
    "accessibility",
    "developer",
    "getting-started",
    "operations",
    "security",
    "user-guide",
)
DOC_TOPICS = ("SERVER_ARCHITECTURE.md",)


def main() -> int:
    HELP.mkdir(parents=True, exist_ok=True)
    for name in ROOT_TOPICS:
        shutil.copy2(ROOT / name, HELP / name)
    for name in DOC_TOPICS:
        shutil.copy2(ROOT / "docs" / name, HELP / name)
    for directory in DOC_TREES:
        destination = HELP / directory
        destination.mkdir(parents=True, exist_ok=True)
        for source in (ROOT / "docs" / directory).glob("*.md"):
            shutil.copy2(source, destination / source.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
