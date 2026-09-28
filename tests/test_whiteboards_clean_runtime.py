"""Acceptance coverage for Whiteboards on the real composed server."""
from __future__ import annotations

import re
from pathlib import Path

from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


def _api(tmp_path: Path) -> OfflineFirstFieldoraApi:
    web_root = Path("src/natureai_next/resources/server_web").resolve()
    return OfflineFirstFieldoraApi(tmp_path / "fieldora.db", web_root=web_root)


def test_clean_composed_server_renders_one_actionable_whiteboards_link(tmp_path):
    api = _api(tmp_path)
    response = api.dispatch("GET", "/", {}, b"")
    assert response.status == 200
    html = response.body.decode("utf-8")
    assert html.count('id="whiteboards-link"') == 1
    match = re.search(r'<button[^>]*id="whiteboards-link"[^>]*>', html)
    assert match
    button = match.group(0)
    assert "hidden" not in button
    assert "disabled" not in button
    assert 'data-fieldora-external-route="/whiteboards/"' in button


def test_clean_composed_server_serves_whiteboards_application(tmp_path):
    api = _api(tmp_path)
    response = api.dispatch("GET", "/whiteboards/?project_id=acceptance-project", {}, b"")
    assert response.status == 200
    assert "Fieldora Whiteboards" in response.body.decode("utf-8")


def test_runtime_click_handler_preserves_selected_project_contract(tmp_path):
    api = _api(tmp_path)
    response = api.dispatch("GET", "/app.js", {}, b"")
    assert response.status == 200
    js = response.body.decode("utf-8")
    assert 'closest?.("#whiteboards-link")' in js
    assert 'resolve?.("projects.context.select")' in js
    assert 'window.location.assign(`/whiteboards/?project_id=${encodeURIComponent(projectId)}`)' in js
