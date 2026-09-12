from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
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
            ("view", "download"),
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


def _seed_media(store: GovernedMediaStore, storage_policy: str) -> MediaRecord:
    payload = b"governed evidence detail payload"
    digest = hashlib.sha256(payload).hexdigest()
    if storage_policy == "referenced":
        record = store.attach_referenced(
            organization_id="local",
            project_id="project-1",
            mime_type="text/plain",
            size_bytes=len(payload),
            sha256=digest,
            source_ref="private-storage-provider-route",
        )
    else:
        upload = store.begin_upload(
            "media-user",
            "local",
            "project-1",
            "private-source-name.txt",
            "text/plain",
            len(payload),
            digest,
        )
        record = store.append_upload(upload, 0, payload)
        assert isinstance(record, MediaRecord)
        if storage_policy == "hybrid":
            attached = store.attach_referenced(
                organization_id="local",
                project_id="project-1",
                mime_type="text/plain",
                size_bytes=len(payload),
                sha256=digest,
                source_ref="private-storage-provider-route",
            )
            assert attached.media_id == record.media_id
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
def _live_server(tmp_path: Path, storage_policy: str):
    store = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "objects")
    record = _seed_media(store, storage_policy)
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


@pytest.mark.parametrize(
    ("storage_policy", "expected_counts"),
    [
        ("managed", (1, 0, 1)),
        ("referenced", (0, 1, 1)),
        ("hybrid", (1, 1, 2)),
    ],
)
def test_library_detail_exposes_only_authorized_governed_identity_and_provenance(
    tmp_path: Path,
    storage_policy: str,
    expected_counts: tuple[int, int, int],
) -> None:
    with _live_server(tmp_path, storage_policy) as (url, record), sync_playwright() as playwright:
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
        managed, referenced, available = expected_counts
        assert payload["storage"] == {
            "storage_policy": storage_policy,
            "managed_instances": managed,
            "referenced_instances": referenced,
            "available_instances": available,
        }
        assert [item["association_type"] for item in payload["associations"]] == [
            "collection",
            "project",
        ]
        assert all("organization_id" not in item for item in payload["associations"])
        serialized = json.dumps(payload)
        assert "private-storage-provider-route" not in serialized
        assert "private-source-name.txt" not in serialized
        assert "relative_path" not in serialized
        assert "source_ref" not in serialized
        assert "organization_id" not in serialized

        detail = page.locator("#media-governed-detail")
        detail.get_by_text("Governed identity", exact=True).wait_for(state="visible")
        assert detail.get_by_text("File instances", exact=True).is_visible()
        policy_detail = detail.locator("p").filter(has_text="Storage policy")
        assert policy_detail.is_visible()
        assert storage_policy.title() in policy_detail.inner_text()
        assert detail.get_by_text("Relationships & provenance", exact=True).is_visible()
        assert detail.get_by_text("Collection / dataset", exact=True).is_visible()
        assert detail.get_by_text("collection-visible", exact=True).is_visible()
        assert detail.get_by_text("Project", exact=True).is_visible()
        assert detail.get_by_text("project-1", exact=True).is_visible()
        download_button = page.locator("#media-download")
        if storage_policy == "referenced":
            assert download_button.count() == 0
        else:
            assert download_button.is_visible()
        direct_status = page.evaluate(
            """async mediaId => {
                const response = await fetch(`/api/v1/media/${encodeURIComponent(mediaId)}`, {
                    headers: {
                        Authorization: "Bearer media-token",
                        "X-Fieldora-Purpose": "research"
                    }
                });
                return response.status;
            }""",
            record.media_id,
        )
        assert direct_status == (404 if storage_policy == "referenced" else 200)
        rendered = page.locator("#media-detail").inner_text()
        assert "dossier-hidden" not in rendered
        assert "private-storage-provider-route" not in rendered
        assert "private-source-name.txt" not in rendered
        if record.relative_path is not None:
            assert record.relative_path not in rendered
        browser.close()
