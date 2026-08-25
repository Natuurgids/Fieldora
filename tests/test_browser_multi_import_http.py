from __future__ import annotations

import contextlib
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from natureai_next.domain.access_control import (
    AccessDecision,
    AccessRequest,
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.http import handler_for
from natureai_next.server.media import GovernedMediaStore


class _Authentication:
    def __init__(self) -> None:
        self.identity = Identity(
            "admin-1",
            IdentityKind.USER,
            "Administrator",
            "local",
            attributes={"platform_admin": "true"},
        )

    def authenticate(self, token: str) -> Identity:
        assert token == "browser-token"
        return self.identity


class _Decisions:
    def __init__(self) -> None:
        self.requests: list[AccessRequest] = []

    def decide(self, request: AccessRequest) -> AccessDecision:
        self.requests.append(request)
        return AccessDecision(True, "test")


class _Science:
    def records(self, collection: str) -> tuple[dict, ...]:
        if collection == "projects":
            return (
                {
                    "id": "project-1",
                    "name": "Import Project",
                    "status": "active",
                    "owner_id": "admin-1",
                    "description": "",
                },
            )
        return ()

    def put(self, collection: str, record: dict, expected_revision: int | None) -> int:
        return 1


def _access_repository(tmp_path: Path) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    repository.put_organization(Organization("local", "Local"))
    repository.put_identity(
        Identity(
            "admin-1",
            IdentityKind.USER,
            "Administrator",
            "local",
            attributes={"platform_admin": "true"},
        )
    )
    for policy in (
        Policy(
            "library-view",
            "View governed evidence",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "admin-1",
            "",
            ("view",),
            ("asset",),
            organization_id="local",
            purposes=("research",),
        ),
        Policy(
            "library-import",
            "Import governed evidence",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "admin-1",
            "",
            ("upload",),
            ("asset",),
            organization_id="local",
            project_id="project-1",
            purposes=("research",),
        ),
        Policy(
            "project-view",
            "View import project",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "admin-1",
            "",
            ("view",),
            ("project",),
            organization_id="local",
            project_id="project-1",
            purposes=("research",),
        ),
    ):
        repository.put_policy(policy)
    return repository


@contextlib.contextmanager
def _live_browser_server(tmp_path: Path):
    media = GovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "objects",
    )
    api = BrowserFunctionalityFieldoraApi(
        _Authentication(),
        _Decisions(),
        _Science(),
        Path("src/natureai_next/resources/server_web"),
        media,
        audit_repository=_access_repository(tmp_path),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(api))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", media
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_multi_file_import_over_real_http_has_no_failed_fetch(tmp_path: Path) -> None:
    with _live_browser_server(tmp_path) as (url, media), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        failed_requests: list[tuple[str, str, str]] = []
        upload_responses: list[tuple[str, str, int]] = []
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                (
                    request.method,
                    request.url,
                    request.failure or "unknown",
                )
            ),
        )
        page.on(
            "response",
            lambda response: upload_responses.append(
                (response.request.method, response.url, response.status)
            )
            if "/api/v1/uploads" in response.url
            else None,
        )
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-token')"
        )
        page.goto(url)
        page.locator("#workspace").wait_for(state="visible")
        page.locator('[data-page="library"]').click()
        page.locator("#page-library").wait_for(state="visible")
        page.evaluate("document.getElementById('upload-project').value='project-1'")
        page.locator("#upload-file").set_input_files(
            [
                {
                    "name": "field-photo.jpg",
                    "mimeType": "image/jpeg",
                    "buffer": b"jpeg evidence bytes",
                },
                {
                    "name": "field-notes.txt",
                    "mimeType": "text/plain",
                    "buffer": b"document evidence bytes",
                },
                {
                    "name": "field-sound.wav",
                    "mimeType": "audio/wav",
                    "buffer": b"audio evidence bytes",
                },
            ]
        )
        page.evaluate("document.getElementById('upload-start').click()")
        page.wait_for_function(
            """
            const node=document.getElementById('upload-status');
            return node.textContent.includes('verified') || node.style.color.includes('danger');
            """,
            timeout=10_000,
        )

        status_text = page.locator("#upload-status").inner_text()
        trace = f"status={status_text!r}, failed={failed_requests!r}, responses={upload_responses!r}"
        assert status_text.startswith("3 files verified"), trace
        assert failed_requests == [], trace
        assert [status for _method, _url, status in upload_responses] == [
            201,
            201,
            201,
            201,
            201,
            201,
        ], trace
        records = media.records("local")
        assert len(records) == 3
        assert {record.mime_type for record in records} == {
            "image/jpeg",
            "text/plain",
            "audio/wav",
        }
        browser.close()
