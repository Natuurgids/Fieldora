from pathlib import Path


INDEX = Path("src/natureai_next/resources/server_web/index.html")


def test_canonical_shell_exposes_whiteboards_navigation():
    html = INDEX.read_text(encoding="utf-8")
    marker = 'data-page="whiteboards"'
    assert html.count(marker) == 1
    assert '>Whiteboards</button>' in html
    assert 'id="page-whiteboards"' in html
