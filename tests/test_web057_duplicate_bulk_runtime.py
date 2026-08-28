from __future__ import annotations

import contextlib
import hashlib
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

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
from natureai_next.server.object_storage import FileObjectStore


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
    def decide(self, _request: AccessRequest) -> AccessDecision:
        return AccessDecision(True, "test")


class _Science:
    def records(self, collection: str) -> tuple[dict, ...]:
        if collection == "projects":
            return (
                {
                    "id": "project-1",
                    "name": "Docker Runtime Project",
                    "status": "active",
                    "owner_id": "admin-1",
                    "description": "",
                },
            )
        return ()

    def put(self, _collection: str, _record: dict, _expected_revision: int | None) -> int:
        return 1


class _FailingFileObjectStore(FileObjectStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fail_sha256 = ""

    def put(self, key: str, source: Path, mime_type: str, sha256: str) -> None:
        if self.fail_sha256 and sha256 == self.fail_sha256:
            raise OSError("WEB-057 injected object-store write failure")
        super().put(key, source, mime_type, sha256)


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
            "View runtime project",
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
    objects = _FailingFileObjectStore(tmp_path / "objects")
    media = GovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "objects",
        object_store=objects,
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
        yield f"http://127.0.0.1:{server.server_port}/", media, objects
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _upload(page: Page, files: list[dict[str, object]], expected: str) -> str:
    page.locator("#upload-file").set_input_files(files)
    page.evaluate("document.getElementById('upload-start').click()")
    deadline = time.monotonic() + 30
    text = ""
    while time.monotonic() < deadline:
        text = page.locator("#upload-status").inner_text()
        if expected in text or "Request failed" in text or "failure" in text.lower():
            break
        page.wait_for_timeout(100)
    return page.locator("#upload-status").inner_text()


def _file(name: str, mime_type: str, payload: bytes) -> dict[str, object]:
    return {"name": name, "mimeType": mime_type, "buffer": payload}


def _record_by_sha(media: GovernedMediaStore, digest: str):
    return next((record for record in media.records("local") if record.sha256 == digest), None)


def test_web057_duplicate_bulk_runtime_graph_inside_docker(tmp_path: Path) -> None:
    photo = b"same governed photo bytes"
    photo_sha = hashlib.sha256(photo).hexdigest()
    large = b"L" * (5 * 1024 * 1024 + 257)
    large_sha = hashlib.sha256(large).hexdigest()
    partial_ok = b"partial success evidence"
    partial_ok_sha = hashlib.sha256(partial_ok).hexdigest()
    partial_fail = b"partial failure evidence"
    partial_fail_sha = hashlib.sha256(partial_fail).hexdigest()

    with _live_browser_server(tmp_path) as (url, media, objects), sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script("sessionStorage.setItem('fieldora-session','browser-token')")
        page.goto(url)
        page.locator("#workspace").wait_for(state="visible")
        page.locator('[data-page="library"]').click()
        page.locator("#page-library").wait_for(state="visible")
        page.evaluate("document.getElementById('upload-project').value='project-1'")

        status = _upload(
            page,
            [
                _file("camera/photo.jpg", "image/jpeg", photo),
                _file("camera/photo-copy.jpg", "image/jpeg", photo),
            ],
            "2 files verified",
        )
        assert status.startswith("2 files verified")
        canonical_photo = _record_by_sha(media, photo_sha)
        assert canonical_photo is not None
        assert len(media.records("local")) == 1
        assert len(media.instances(canonical_photo.media_id, "local")) == 1

        status = _upload(
            page,
            [_file("second-path/renamed-photo.jpg", "image/jpeg", photo)],
            "1 file verified",
        )
        assert status.startswith("1 file verified")
        assert len(media.records("local")) == 1
        assert _record_by_sha(media, photo_sha).media_id == canonical_photo.media_id

        status = _upload(
            page,
            [
                _file("notes.txt", "text/plain", b"mixed text evidence"),
                _file("sound.wav", "audio/wav", b"mixed audio evidence"),
                _file("duplicate-again.jpg", "image/jpeg", photo),
            ],
            "3 files verified",
        )
        assert status.startswith("3 files verified")
        assert len(media.records("local")) == 3
        assert {record.mime_type for record in media.records("local")} == {
            "image/jpeg",
            "text/plain",
            "audio/wav",
        }

        status = _upload(
            page,
            [_file("large.bin", "application/octet-stream", large)],
            "1 file verified",
        )
        assert status.startswith("1 file verified")
        large_record = _record_by_sha(media, large_sha)
        assert large_record is not None
        assert large_record.size_bytes == len(large)
        assert len(media.records("local")) == 4

        objects.fail_sha256 = partial_fail_sha
        status = _upload(
            page,
            [
                _file("partial-ok.txt", "text/plain", partial_ok),
                _file("partial-fail.bin", "application/octet-stream", partial_fail),
            ],
            "2 files verified",
        )
        assert not status.startswith("2 files verified")
        assert _record_by_sha(media, partial_ok_sha) is not None
        assert _record_by_sha(media, partial_fail_sha) is None
        assert len(media.records("local")) == 5

        records = media.records("local")
        for record in records:
            links = media.associations.links(record.media_id, "local")
            assert [(link.association_type, link.target_id) for link in links] == [
                ("project", "project-1")
            ]
        assert _record_by_sha(media, photo_sha).media_id == canonical_photo.media_id
        assert len(media.instances(canonical_photo.media_id, "local")) == 1
        browser.close()
