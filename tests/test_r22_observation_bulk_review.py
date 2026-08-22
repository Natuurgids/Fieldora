from __future__ import annotations

from natureai_next.application.ai_review import ReviewFilter, SuggestionService
from natureai_next.domain.ai import ReviewBatchResult, SuggestionPage


class _Store:
    def __init__(self) -> None:
        self.batch_calls: list[tuple[tuple[str, ...], str]] = []

    def page_for_asset(self, asset_public_id: str, **kwargs: object) -> SuggestionPage:
        assert asset_public_id == "asset-1"
        cursor = kwargs.get("cursor")
        if cursor is None:
            return SuggestionPage(items=(_item("s1", "asset-1"), _item("s2", "asset-1")), next_cursor=2)
        return SuggestionPage(items=(_item("s3", "asset-1"),), next_cursor=None)

    def batch_review(self, ids, *, action, action_id_factory, now_us, reason=None):
        del action_id_factory, now_us, reason
        values = tuple(ids)
        self.batch_calls.append((values, action))
        return ReviewBatchResult(reviewed=values, failed=())


def _item(public_id: str, asset_id: str):
    from natureai_next.domain.ai import ConfidenceBand, SuggestionProjection, SuggestionReviewState

    return SuggestionProjection(
        public_id=public_id,
        asset_public_id=asset_id,
        candidate_taxon_public_id="taxon",
        candidate_label="Taxon",
        raw_score=0.5,
        calibrated_score=0.5,
        rank=1,
        confidence_band=ConfidenceBand.HIGH,
        taxonomic_level="species",
        review_state=SuggestionReviewState.PENDING,
        provenance_json="{}",
    )


def test_reject_all_pending_keeps_each_suggestion_linked_and_reviews_all_pages() -> None:
    store = _Store()
    service = SuggestionService(store)  # type: ignore[arg-type]
    result = service.reject_all_pending_for_asset(
        "asset-1", action_id_factory=lambda: "action", now_us=1
    )
    assert result.reviewed == ("s1", "s2", "s3")
    assert store.batch_calls == [(("s1", "s2", "s3"), "reject")]


def test_ui_uses_extended_selection_and_bulk_actions() -> None:
    source = open("src/natureai_next/ui/qt/ai_review.py", encoding="utf-8").read()
    assert "SelectionMode.ExtendedSelection" in source
    assert "def _selected_ids" in source
    assert "def _apply_selected" in source
    assert "Accept one; reject remaining" in source
    assert "Reject all unconfirmed" in source
