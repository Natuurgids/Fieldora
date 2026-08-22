from pathlib import Path


def test_batch_review_navigation_uses_existing_selection_helper() -> None:
    source = Path("src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
    assert "self._select_public_id(" not in source
    assert "def _select_review_item(self, public_id: str) -> bool:" in source
    assert "self._select_review_item(target.public_id)" in source
    assert "Qt.ItemDataRole.UserRole" in source


def test_batch_action_semantics_remain_explicit() -> None:
    source = Path("src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
    all_block = source[
        source.index("def _accept_all_pending_and_next") : source.index(
            "def _accept_and_reject_rest"
        )
    ]
    only_block = source[
        source.index("def _accept_and_reject_rest") : source.index("def _reject_other_options")
    ]
    assert "accept_all_pending_for_asset" in all_block
    assert "_advance_to_next_pending_photo" in all_block
    assert "accept_and_reject_others" in only_block
    assert "_advance_to_next_pending_photo" in only_block
