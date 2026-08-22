"""Paged library presentation model with stale-response suppression."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.application.catalog_browsing import CatalogQueryService
from natureai_next.ports.catalog_queries import AssetGridRow
from natureai_next.ui.presentation.selection import SelectionModel


@dataclass(frozen=True, slots=True)
class LibraryState:
    generation: int
    rows: tuple[AssetGridRow, ...]
    total_count: int
    next_cursor: int | None
    loading: bool
    error: str | None


class LibraryPresenter:
    def __init__(self, service: CatalogQueryService, page_size: int = 200) -> None:
        if not 1 <= page_size <= 500:
            raise ValueError("invalid page size")
        self._service = service
        self._page_size = page_size
        self._generation = 0
        self.selection = SelectionModel()
        self.state = LibraryState(0, (), 0, None, False, None)

    def begin_refresh(self) -> int:
        self._generation += 1
        self.state = LibraryState(self._generation, (), 0, None, True, None)
        return self._generation

    def complete_refresh(self, generation: int) -> bool:
        if generation != self._generation:
            return False
        try:
            page = self._service.page(limit=self._page_size)
        except Exception as exc:
            self.state = LibraryState(generation, (), 0, None, False, str(exc))
            return True
        self.state = LibraryState(
            generation, page.rows, page.total_count, page.next_cursor, False, None
        )
        self.selection.retain_existing({r.public_id for r in page.rows})
        return True

    def refresh(self) -> None:
        self.complete_refresh(self.begin_refresh())

    def load_more(self) -> None:
        cursor = self.state.next_cursor
        if cursor is None or self.state.loading:
            return
        try:
            page = self._service.page(limit=self._page_size, after_id=cursor)
        except Exception as exc:
            self.state = LibraryState(
                self._generation, self.state.rows, self.state.total_count, cursor, False, str(exc)
            )
            return
        self.state = LibraryState(
            self._generation,
            self.state.rows + page.rows,
            page.total_count,
            page.next_cursor,
            False,
            None,
        )
