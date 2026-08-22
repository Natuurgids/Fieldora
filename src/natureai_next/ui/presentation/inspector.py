"""Draft-based inspector editing and semantic undo/redo."""

from __future__ import annotations

from dataclasses import dataclass, replace

from natureai_next.application.catalog_browsing import (
    CatalogEditService,
    CatalogQueryService,
    UndoableMetadataCommand,
)
from natureai_next.ports.catalog_queries import AssetDetail, MetadataPatch


@dataclass(frozen=True, slots=True)
class InspectorDraft:
    public_id: str
    revision: int
    title: str | None
    caption: str | None
    user_notes: str | None
    rating: int | None
    color_label: str | None
    pick_state: str | None
    dirty: bool = False


class InspectorPresenter:
    def __init__(self, queries: CatalogQueryService, edits: CatalogEditService) -> None:
        self._queries = queries
        self._edits = edits
        self.detail: AssetDetail | None = None
        self.draft: InspectorDraft | None = None
        self._undo: list[UndoableMetadataCommand] = []
        self._redo: list[UndoableMetadataCommand] = []

    def load(self, public_id: str) -> None:
        d = self._queries.detail(public_id)
        self.detail = d
        self.draft = (
            None
            if d is None
            else InspectorDraft(
                d.public_id,
                d.revision,
                d.title,
                d.caption,
                d.user_notes,
                d.rating,
                d.color_label,
                d.pick_state,
            )
        )

    def edit(self, **changes: object) -> None:
        if self.draft is None:
            raise RuntimeError("no asset loaded")
        allowed = {"title", "caption", "user_notes", "rating", "color_label", "pick_state"}
        if not set(changes) <= allowed:
            raise ValueError("unsupported field")
        self.draft = replace(self.draft, **changes, dirty=True)

    def validate(self) -> tuple[str, ...]:
        if self.draft is None:
            return ("no asset loaded",)
        errors = []
        if self.draft.rating is not None and not 0 <= self.draft.rating <= 5:
            errors.append("rating must be between 0 and 5")
        for name, limit in [("title", 500), ("caption", 10000), ("user_notes", 50000)]:
            value = getattr(self.draft, name)
            if value is not None and len(value) > limit:
                errors.append(f"{name} exceeds {limit} characters")
        return tuple(errors)

    def commit(self) -> None:
        if self.draft is None:
            return
        errors = self.validate()
        if errors:
            raise ValueError("; ".join(errors))
        p = MetadataPatch(
            self.draft.title,
            self.draft.caption,
            self.draft.user_notes,
            self.draft.rating,
            self.draft.color_label,
            self.draft.pick_state,
        )
        command = self._edits.update(
            public_id=self.draft.public_id, expected_revision=self.draft.revision, patch=p
        )
        self._undo.append(command)
        self._redo.clear()
        self.load(self.draft.public_id)

    def cancel(self) -> None:
        if self.detail is not None:
            self.load(self.detail.public_id)

    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo.pop()
        change = command.change
        reverse = self._edits.update(
            public_id=change.public_id, expected_revision=change.new_revision, patch=change.before
        )
        self._redo.append(reverse)
        self.load(change.public_id)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        reverse = self._redo.pop()
        change = reverse.change
        reapplied = self._edits.update(
            public_id=change.public_id, expected_revision=change.new_revision, patch=change.before
        )
        self._undo.append(reapplied)
        self.load(change.public_id)
        return True
