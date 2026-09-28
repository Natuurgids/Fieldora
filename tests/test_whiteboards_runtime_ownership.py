from pathlib import Path


def test_runtime_ownership_contract_is_documented_and_canonical():
    html = Path("src/natureai_next/resources/server_web/index.html").read_text(encoding="utf-8")
    docs = Path("docs/whiteboards-runtime-architecture.md").read_text(encoding="utf-8")
    assert html.count('id="whiteboards-link"') == 1
    assert "canonical server shell owns the single rendered `#whiteboards-link`" in docs
    assert "composed `OfflineFirstFieldoraApi`" in docs
