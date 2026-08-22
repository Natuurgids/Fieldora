"""Identity-based selection independent of paging and widgets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectionSnapshot:
    selected_ids: frozenset[str]
    anchor_id: str | None
    current_id: str | None


class SelectionModel:
    def __init__(self) -> None:
        self._selected: set[str] = set()
        self._anchor: str | None = None
        self._current: str | None = None

    @property
    def snapshot(self) -> SelectionSnapshot:
        return SelectionSnapshot(frozenset(self._selected), self._anchor, self._current)

    def clear(self) -> None:
        self._selected.clear()
        self._anchor = None
        self._current = None

    def select_one(self, public_id: str) -> None:
        self._selected = {public_id}
        self._anchor = public_id
        self._current = public_id

    def toggle(self, public_id: str) -> None:
        if public_id in self._selected:
            self._selected.remove(public_id)
        else:
            self._selected.add(public_id)
        self._anchor = self._anchor or public_id
        self._current = public_id

    def select_range(self, ordered_ids: tuple[str, ...], target_id: str) -> None:
        if target_id not in ordered_ids:
            return
        anchor = self._anchor if self._anchor in ordered_ids else target_id
        a, b = ordered_ids.index(anchor), ordered_ids.index(target_id)
        self._selected.update(ordered_ids[min(a, b) : max(a, b) + 1])
        self._current = target_id
        self._anchor = anchor

    def retain_existing(self, existing_ids: set[str]) -> None:
        self._selected.intersection_update(existing_ids)
        if self._anchor not in existing_ids:
            self._anchor = None
        if self._current not in existing_ids:
            self._current = None
