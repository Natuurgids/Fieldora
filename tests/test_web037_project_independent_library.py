from __future__ import annotations

import hashlib
from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.media import GovernedMediaStore, MediaRecord


def _complete_upload(
    api: BrowserFunctionalityFieldoraApi,
    store: GovernedMediaStore,
    payload: bytes,
    *,
    project_id: str,
) -> MediaRecord:
    upload = store.begin_upload(
        "researcher-1",
        "organization-1",
        project_id,
        "evidence.bin",
        "application/octet-stream",
        len(payload),
        hashlib.sha256(payload).hexdigest(),
    )
    record = store.append_upload(upload, 0, payload)
    assert isinstance(record, MediaRecord)
    api._link_completed_upload(
        upload,
        {"x-fieldora-purpose": "research"},
        ApiResponse.json(201, {"media_id": record.media_id}),
    )
    return record


def test_general_library_evidence_exists_without_project_and_project_is_only_a_link(
    tmp_path: Path,
) -> None:
    store = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "objects")
    api = BrowserFunctionalityFieldoraApi.__new__(BrowserFunctionalityFieldoraApi)
    api._media = store
    payload = b"project-independent governed Library evidence"

    general = _complete_upload(api, store, payload, project_id="")

    assert general.project_id == ""
    assert store.records("organization-1") == (general,)
    assert store.associations.links(general.media_id, "organization-1") == ()

    project_context = _complete_upload(api, store, payload, project_id="project-1")

    assert project_context.media_id == general.media_id
    assert store.record(general.media_id) == general
    assert store.record(general.media_id).project_id == ""
    assert len(store.records("organization-1")) == 1
    links = store.associations.links(general.media_id, "organization-1")
    assert [(link.association_type, link.target_id) for link in links] == [
        ("project", "project-1")
    ]
