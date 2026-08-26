from __future__ import annotations

import contextlib
import hashlib
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from natureai_next.application.access_control import PolicyDecisionService
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Organization,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.http import handler_for
from natureai_next.server.linked_storage_browser_api import LinkedStorageBrowserFieldoraApi
from natureai_next.server.media import GovernedMediaStore, MediaRecord
from natureai_next.server.media_links import new_association


class _Authentication:
    def __init__(self) -> None:
        self.identity = Identity(
            "media-user",
            IdentityKind.USER,
            "Media Researcher",
            "local",
        )

    def authenticate(self, token: str) -> Identity:
        assert token == "media-token"
        return self.identity


class _Science:
    def records(self, collection: str) -> tuple[dict, ...]:
        if collection == "projects":
            return (
                {
                    "id": "project-1",
                    "name": "Governed Evidence Project",
                    "status": "active",
                    "owner_id": "media-user",
                    "description": "",
                },
            )
        return ()

    def put(self, _collection: str, _record: dict, _expected_revision: int | None) -> int:
        return 1


def _access_repository(tmp_path: Path) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    repository.put_organization(Organization("local", "Local"))
    repository.put_identity(
        Identity("media-user", IdentityKind.USER, "Media Researcher", "local")
    )
    for policy in (
        Policy(
            "media-view",
            "View governed evidence",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "media-user",
            "",
            ("view",),
            ("asset",),
            organization_id="local",
            purposes=("research",),
        ),
        Policy(
            "project-view",
            "View evidence project relationship",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "media-user",
            "",
            ("view",),
            ("project",),
            organization_id="local",
            project_id="project-1",
            purposes=("research",),
        ),
        Policy(
            "collection-view",
            "View collection relationship",
            PolicyEffect.ALLOW,
            PolicySource.DIRECT,
            "test",
            "media-user",
            "",
            ("view",),
            ("collection",),
            organization_id="local",
            project_id="project-1",
            purposes=("research",),
        ),
    ):
        repository.put_policy(policy)
    return repository


def _seed_media(store: GovernedMediaStore) -> MediaRecord:
    payload = b"governed evidence detail payload"
    upload = store.begin_upload(
        "media-user",
        "local",
        "project-1",
        "private-source-name.txt",
        "text/plain",
        len(payload),
        hashlib.sha256(payload).hexdigest(),
    )
    record = store.append_upload(upload, 0, payload)
    assert isinstance(record, MediaRecord)
    for association_type, target_id in (
        ("project", "project-1"),
        ("collection", "collection-visible"),
        ("dossier", "dossier-hidden"),
    ):
        store.associations.link(
            new_association(
                media_id=record.media_id,
                organization_id="local",
                association_type=association_type,
                target_id=target_id,
                purpose="research",
                linked_by="media-user",
            )
        )
    return record


@contextlib.contextmanager
def _live_server(tmp_path: Path):
    store = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "objects")
    record = _seed_media(store)
    access = _access_repository(tmp_path)
    api = LinkedStorageBrowserFieldoraApi(
        _Authentication(),
        PolicyDecisionService(access),
        _Science(),
        Path("src/natureai_next/resources/server_web"),
        store,
        audit_repository=access,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(api))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", record
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_library_detail_exposes_only_authorized_governed_identity_and_provenance(
    tmp_path: Path,
) -> None:
    with _live_server(tmp_path) as (url, record), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script("sessionStorage.setItem('fieldora-session','media-token')")
        page.goto(url)
        page.wait_for_function("document.body.dataset.fieldoraCapabilities === 'ready'")
        page.locator('[data-page="library"]').click()
        page.locator("#page-library").wait_for(state="visible")
        media_card = page.locator(f'[data-media="{record.media_id}"]')
        media_card.wait_for(state="visible")

        with page.expect_response(
            lambda response: response.request.method == "GET"
            and f"/api/v1/media/{record.media_id}/detail" in response.url
        ) as detail_info:
            media_card.click()
        response = detail_info.value
        payload = response.json()

        assert response.status == 200
        assert set(payload["item"]) == {"media_id", "mime_type", "size_bytes", "sha256"}
        assert payload["item"]["media_id"] == record.media_id
        assert payload["item"]["sha256"] == record.sha256
        assert [item["association_type"] for item in payload["associations"]] == [
            "collection",
            "project",
        ]
        assert all("organization_id" not in item for item in payload["associations"])

        detail = page.locator("#media-governed-detail")
        detail.get_by_text("Governed identity", exact=True).wait_for(state="visible")
        assert detail.get_by_text("Relationships & provenance", exact=True).is_visible()
        assert detail.get_by_text("Collection / dataset", exact=True).is_visible()
        assert detail.get_by_text("collection-visible", exact=True).is_visible()
        assert detail.get_by_text("Project", exact=True).is_visible()
        assert detail.get_by_text("project-1", exact=True).is_visible()
        assert "dossier-hidden" not in detail.inner_text()
        assert record.relative_path not in page.locator("#media-detail").inner_text()
        assert "private-source-name.txt" not in page.locator("#media-detail").inner_text()
        browser.close()
