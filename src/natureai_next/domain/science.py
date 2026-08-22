"""Dependency-free contracts for Fieldora Science."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScienceEntityType(StrEnum):
    PROJECT = "project"
    DOSSIER = "dossier"
    ARTIFACT = "artifact"
    WHITEBOARD = "whiteboard"
    ACTIVITY = "activity"
    RESOURCE = "resource"


@dataclass(frozen=True, slots=True)
class ScienceRevision:
    database_revision: int

    def next(self) -> "ScienceRevision":
        return ScienceRevision(self.database_revision + 1)


class ScienceRevisionConflict(RuntimeError):
    """Raised when a writer is based on an older Science database revision."""

