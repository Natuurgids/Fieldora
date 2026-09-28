from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.excalidraw_web import ExcalidrawWebMixin


def test_canonical_server_sidebar_contains_whiteboards_destination() -> None:
    html = Path("src/natureai_next/resources/server_web/index.html").read_text(encoding="utf-8")
    assert html.count('id="whiteboards-link"') == 1
    assert 'data-fieldora-external-route="/whiteboards/"' in html
    assert html.index('id="whiteboards-link"') < html.index("Help &amp; Guides")


def test_excalidraw_shell_does_not_duplicate_canonical_whiteboards_link() -> None:
    html = Path("src/natureai_next/resources/server_web/index.html").read_bytes()
    response = ExcalidrawWebMixin._excalidraw_shell_link(
        ApiResponse(200, html, "text/html; charset=utf-8")
    )
    assert response.body.count(b'id="whiteboards-link"') == 1

def test_whiteboards_click_contract_carries_selected_project() -> None:
    response = ExcalidrawWebMixin._excalidraw_shell_script(
        ApiResponse(200, b"", "text/javascript; charset=utf-8")
    )
    script = response.body.decode("utf-8")
    assert 'closest?.("#whiteboards-link")' in script
    assert 'resolve?.("projects.context.select")' in script
    assert '/whiteboards/?project_id=${encodeURIComponent(projectId)}' in script
