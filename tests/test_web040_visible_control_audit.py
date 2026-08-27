from __future__ import annotations

import contextlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.visible_control_audit_api import VisibleControlAuditApiMixin
from natureai_next.server.visible_control_audit_web import (
    patch_visible_control_audit_response,
)


@contextlib.contextmanager
def _fixture(tmp_path: Path):
    html = """<!doctype html><html><body>
    <section id="knowledge-review-panel">
      <section class="card">
        <div class="tabs">
          <button>Review queue</button><button>Accepted knowledge</button>
        </div>
        <article data-knowledge-proposal="proposal-1">
          <div class="actions">
            <button data-knowledge-review="accept">Accept</button>
            <button data-knowledge-review="reject">Reject</button>
            <button data-knowledge-review="defer">Defer</button>
          </div>
        </article>
      </section>
    </section>
    <div id="knowledge-workspace-nav">
      <button data-task-view="review">Review knowledge</button>
      <button data-task-view="add">Add identification</button>
    </div>
    <script src="/app.js"></script>
    </body></html>"""
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    response = patch_visible_control_audit_response(
        "/app.js", ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    )
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_visible_control_audit_wraps_final_managed_composition() -> None:
    assert OfflineFirstFieldoraApi.__mro__[1] is VisibleControlAuditApiMixin


def test_patch_is_idempotent_and_only_targets_app_bundle() -> None:
    base = ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    once = patch_visible_control_audit_response("/app.js", base)
    twice = patch_visible_control_audit_response("/app.js", once)
    assert once.body == twice.body
    assert b"__fieldoraVisibleControlAuditWired" in once.body

    api = ApiResponse.json(200, {"items": []})
    assert patch_visible_control_audit_response("/api/v1/knowledge", api) == api


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_dead_knowledge_pseudo_tabs_are_removed_but_real_review_controls_remain(
    tmp_path: Path,
    browser_name: str,
) -> None:
    with _fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        assert page.locator("#knowledge-review-panel > section.card > .tabs").count() == 0
        assert page.get_by_role("button", name="Review queue", exact=True).count() == 0
        assert page.get_by_role("button", name="Accepted knowledge", exact=True).count() == 0

        assert page.locator("#knowledge-workspace-nav button").all_inner_texts() == [
            "Review knowledge",
            "Add identification",
        ]
        assert page.locator("[data-knowledge-review]").all_inner_texts() == [
            "Accept",
            "Reject",
            "Defer",
        ]
        browser.close()
