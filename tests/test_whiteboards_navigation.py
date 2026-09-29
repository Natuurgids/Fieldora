from pathlib import Path


INDEX = Path("src/natureai_next/resources/server_web/index.html")


def test_canonical_shell_exposes_single_governed_whiteboards_navigation():
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('id="whiteboards-link"') == 1
    assert html.count('>Whiteboards</button>') == 1
    assert 'data-fieldora-external-route="/whiteboards/"' in html
    assert 'data-page="whiteboards"' not in html
    assert 'href="/excalidraw/"' not in html

# This test intentionally gates the clean canonical navigation path.


def test_desktop_alignment_preserves_whiteboards_before_rebuilding_sidebar():
    patch = Path("src/natureai_next/server/desktop_alignment_web.py").read_text(
        encoding="utf-8"
    )
    capture = 'const whiteboards=document.getElementById("whiteboards-link");'
    rebuild = "sidebar.replaceChildren();"
    append = "if(whiteboards)sidebar.appendChild(whiteboards);"

    assert patch.count(capture) == 1
    assert patch.count(append) == 1
    assert patch.index(capture) < patch.index(rebuild) < patch.index(append)
