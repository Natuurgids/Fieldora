from pathlib import Path


def test_bioclip_accept_handlers_preserve_result_status_and_advance() -> None:
    source = Path("src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
    assert (
        'if action == "accept":'
        not in source[
            source.index("def _accept_and_reject_rest") : source.index("def _reject_other_options")
        ]
    )
    assert "Accepted the selected suggestion and rejected" in source
    assert (
        "Accepted {len(result.reviewed)} pending suggestion(s); opened the next photograph."
        in source
    )
    assert "messages = {" in source
    assert "Suggestion accepted and enrichment recorded." in source


def test_acceptance_store_batches_are_atomic_and_state_specific() -> None:
    source = Path("src/natureai_next/infrastructure/database/ai_review.py").read_text(
        encoding="utf-8"
    )
    assert "WHERE asset_id=? AND review_state='pending'" in source
    assert 'action="accept"' in source
    assert 'action="reject"' in source
    assert 'connection.execute("BEGIN IMMEDIATE")' in source
    assert 'connection.execute("COMMIT")' in source
