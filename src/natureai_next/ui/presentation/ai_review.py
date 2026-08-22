"""GUI-independent virtualized AI review presentation state."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.application.ai_review import ReviewFilter, SuggestionService
from natureai_next.domain.ai import SuggestionPage, SuggestionProjection


@dataclass(frozen=True, slots=True)
class AIReviewState:
    items: tuple[SuggestionProjection, ...] = ()
    next_cursor: int | None = None
    selected_public_id: str | None = None
    loading: bool = False
    error: str | None = None


class AIReviewModel:
    def __init__(self, service: SuggestionService, page_size: int = 100) -> None:
        self._service = service
        self._page_size = max(1, min(page_size, 500))
        self.state = AIReviewState()
        self.filter = ReviewFilter()
        self.asset_public_id: str | None = None

    @property
    def page_size(self) -> int:
        return self._page_size

    def apply_page(self, page: SuggestionPage) -> AIReviewState:
        self.state = AIReviewState(page.items, page.next_cursor, None, False, None)
        return self.state

    def set_error(self, message: str) -> AIReviewState:
        self.state = AIReviewState(error=message)
        return self.state

    def refresh(self, filter: ReviewFilter | None = None) -> AIReviewState:
        if filter is not None:
            self.filter = filter
        self.asset_public_id = None
        return self._refresh_page()

    def refresh_asset(
        self,
        asset_public_id: str,
        filter: ReviewFilter | None = None,
    ) -> AIReviewState:
        if filter is not None:
            self.filter = filter
        self.asset_public_id = asset_public_id
        return self._refresh_page()

    def _refresh_page(self) -> AIReviewState:
        try:
            if self.asset_public_id is None:
                page = self._service.page(filter=self.filter, page_size=self._page_size)
            else:
                page = self._service.page_for_asset(
                    self.asset_public_id,
                    filter=self.filter,
                    page_size=self._page_size,
                )
            self.state = AIReviewState(page.items, page.next_cursor, None, False, None)
        except Exception as exc:
            self.state = AIReviewState(error=str(exc))
        return self.state

    def load_more(self) -> AIReviewState:
        if self.state.next_cursor is None:
            return self.state
        if self.asset_public_id is None:
            page = self._service.page(
                filter=self.filter,
                cursor=self.state.next_cursor,
                page_size=self._page_size,
            )
        else:
            page = self._service.page_for_asset(
                self.asset_public_id,
                filter=self.filter,
                cursor=self.state.next_cursor,
                page_size=self._page_size,
            )
        self.state = AIReviewState(
            self.state.items + page.items,
            page.next_cursor,
            self.state.selected_public_id,
        )
        return self.state

    def select(self, public_id: str | None) -> AIReviewState:
        self.state = AIReviewState(
            self.state.items,
            self.state.next_cursor,
            public_id,
            self.state.loading,
            self.state.error,
        )
        return self.state
