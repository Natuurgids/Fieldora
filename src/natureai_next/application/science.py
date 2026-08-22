"""Application contracts for incrementally evolving Fieldora Science."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from natureai_next.domain.science import ScienceEntityType, ScienceRevision


@dataclass(frozen=True, slots=True)
class ScienceRecord:
    entity_type: ScienceEntityType
    public_id: str
    revision: int
    payload: dict[str, object]


class ScienceRepository(Protocol):
    """Persistence boundary used by future CLI, Qt, sync, and web adapters."""

    def database_revision(self) -> ScienceRevision: ...

    def get(self, entity_type: ScienceEntityType, public_id: str) -> ScienceRecord: ...

    def list(self, entity_type: ScienceEntityType) -> tuple[ScienceRecord, ...]: ...

    def put(
        self, record: ScienceRecord, *, expected_revision: int | None
    ) -> ScienceRecord: ...

    def delete(
        self, entity_type: ScienceEntityType, public_id: str, *, expected_revision: int
    ) -> None: ...


class ScienceSnapshotRepository(Protocol):
    def load_snapshot(self) -> tuple[dict, ScienceRevision]: ...

    def save_snapshot(
        self, snapshot: dict, *, expected_revision: ScienceRevision
    ) -> ScienceRevision: ...


def default_science_snapshot() -> dict:
    return {
        "schema_version": 4,
        "projects": [],
        "board": [],
        "activities": [],
        "artifacts": [],
        "dossiers": [],
        "project_stages": [],
        "project_activities": [],
        "project_resources": [],
        "project_budgets": [],
        "board_shapes": [],
        "whiteboards": [],
        "whiteboard_elements": [],
        "dossier_whiteboards": [],
        "dossier_links": [],
    }


class ScienceSession:
    """One application-owned revision and snapshot shared by every Science view."""

    def __init__(self, repository: ScienceSnapshotRepository) -> None:
        self._repository = repository
        self.data, self.revision = repository.load_snapshot()

    def save(self) -> ScienceRevision:
        self.revision = self._repository.save_snapshot(
            self.data, expected_revision=self.revision
        )
        return self.revision
