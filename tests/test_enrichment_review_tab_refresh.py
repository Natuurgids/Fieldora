from pathlib import Path


def test_multimodal_review_refreshes_newly_selected_media_tab() -> None:
    source = Path("src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")

    assert "self._tabs.currentChanged.connect(self._refresh_selected_review)" in source
    assert "def _refresh_selected_review(self, _index: int) -> None:" in source
    assert 'hasattr(current, "refresh")' in source
    assert "current.refresh()" in source
