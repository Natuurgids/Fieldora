from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.server.api import FieldoraApi, ScienceReadProjection
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.pagination_api import (
    PaginationApiMixin,
    patch_pagination_web_response,
)

ROOT = Path(__file__).parents[1]
WEB_ROOT = ROOT / "src/natureai_next/resources/server_web"


class _Authentication:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")

    def authenticate(self, token: str) -> Identity:
        assert token == "page-token"
        return self.identity


class _Decisions:
    def decide(self, request):
        if request.action == "view_audit":
            return SimpleNamespace(allowed=True)
        return SimpleNamespace(allowed="denied" not in request.resource_id)


class _PagedApi(PaginationApiMixin, FieldoraApi):
    pass


def _science(tmp_path: Path) -> ScienceReadProjection:
    database = tmp_path / "science.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE science_records("
            "collection_name TEXT NOT NULL,record_id TEXT NOT NULL,payload_json TEXT NOT NULL,"
            "record_revision INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,"
            "PRIMARY KEY(collection_name,record_id))"
        )
        records = {
            "projects": [
                ("p-1", {"id": "p-1", "name": "One"}),
                ("p-denied", {"id": "p-denied", "name": "Hidden"}),
                ("p-2", {"id": "p-2", "name": "Two"}),
                ("p-3", {"id": "p-3", "name": "Three"}),
            ],
            "server_observations": [
                ("o-1", {"id": "o-1", "project_id": "p-1"}),
                ("o-denied", {"id": "o-denied", "project_id": "p-1"}),
                ("o-2", {"id": "o-2", "project_id": "p-1"}),
                ("o-3", {"id": "o-3", "project_id": "p-1"}),
            ],
        }
        timestamp = 1
        for collection, values in records.items():
            for record_id, payload in values:
                connection.execute(
                    "INSERT INTO science_records VALUES(?,?,?,?,?)",
                    (collection, record_id, json.dumps(payload), 1, timestamp),
                )
                timestamp += 1
        connection.commit()
    finally:
        connection.close()
    return ScienceReadProjection(database)


def _media(tmp_path: Path) -> GovernedMediaStore:
    database = tmp_path / "media.sqlite3"
    store = GovernedMediaStore(database, tmp_path / "objects")
    connection = sqlite3.connect(database)
    try:
        for media_id in ("m-z", "m-y-denied", "m-x", "m-w"):
            connection.execute(
                "INSERT INTO governed_media VALUES(?,?,?,?,?,?,?)",
                (
                    media_id,
                    None,
                    "local",
                    "p-1",
                    "image/jpeg",
                    10,
                    (media_id.encode().hex() + "0" * 64)[:64],
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return store


def _audit(tmp_path: Path) -> SqliteAccessControlRepository:
    repository = SqliteAccessControlRepository(tmp_path / "access.sqlite3")
    connection = repository._factory.connect()
    try:
        for sequence, organization_id in (
            (1, "local"),
            (2, "foreign"),
            (3, "local"),
            (4, "foreign"),
            (5, "local"),
        ):
            connection.execute(
                "INSERT INTO access_audit_events("
                "sequence,occurred_at_utc,subject_id,action,resource_type,resource_id,"
                "allowed,reason,policy_ids_json,request_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    f"2026-08-28T00:00:0{sequence}+00:00",
                    "actor",
                    "view",
                    "asset",
                    f"asset-{sequence}",
                    1,
                    "allowed",
                    "[]",
                    json.dumps({"organization_id": organization_id}),
                ),
            )
    finally:
        connection.close()
    return repository


def _api(tmp_path: Path) -> _PagedApi:
    return _PagedApi(
        _Authentication(),
        _Decisions(),
        _science(tmp_path),
        WEB_ROOT,
        _media(tmp_path),
        audit_repository=_audit(tmp_path),
    )


def _get(api: _PagedApi, path: str, *, purpose: str = "research") -> dict:
    response = api.dispatch(
        "GET",
        path,
        {"authorization": "Bearer page-token", "x-fieldora-purpose": purpose},
        b"",
    )
    assert response.status == 200
    return json.loads(response.body)


def test_web047_named_lists_page_without_disclosing_denied_rows(tmp_path: Path) -> None:
    api = _api(tmp_path)

    projects = _get(api, "/api/v1/projects?limit=2")
    assert [item["id"] for item in projects["items"]] == ["p-1", "p-2"]
    assert projects["count"] == 2
    assert projects["next_cursor"]
    projects_next = _get(
        api, f'/api/v1/projects?limit=2&after={projects["next_cursor"]}'
    )
    assert [item["id"] for item in projects_next["items"]] == ["p-3"]
    assert projects_next["next_cursor"] == ""

    observations = _get(api, "/api/v1/observations?limit=2")
    assert [item["id"] for item in observations["items"]] == ["o-1", "o-2"]
    assert observations["next_cursor"]

    media = _get(api, "/api/v1/media?limit=2")
    assert [item["media_id"] for item in media["items"]] == ["m-z", "m-x"]
    assert media["count"] == 2
    assert media["next_cursor"]

    audit = _get(api, "/api/v1/audit?limit=2", purpose="administration")
    assert [item["sequence"] for item in audit["items"]] == [5, 3]
    assert audit["count"] == 2
    assert audit["next_cursor"]
    assert "total" not in audit
    audit_next = _get(
        api,
        f'/api/v1/audit?limit=2&after={audit["next_cursor"]}',
        purpose="administration",
    )
    assert [item["sequence"] for item in audit_next["items"]] == [1]
    assert audit_next["next_cursor"] == ""


def test_web047_invalid_cursor_and_limit_fail_closed(tmp_path: Path) -> None:
    api = _api(tmp_path)
    headers = {"authorization": "Bearer page-token"}
    invalid_cursor = api.dispatch(
        "GET", "/api/v1/projects?after=not-a-cursor", headers, b""
    )
    assert invalid_cursor.status == 400
    assert json.loads(invalid_cursor.body) == {"error": "invalid_cursor"}
    invalid_limit = api.dispatch("GET", "/api/v1/projects?limit=101", headers, b"")
    assert invalid_limit.status == 400
    assert json.loads(invalid_limit.body) == {"error": "invalid_limit"}


def test_web047_managed_composition_and_client_use_bounded_load_more_pages() -> None:
    assert issubclass(OfflineFirstFieldoraApi, PaginationApiMixin)
    response = patch_pagination_web_response(
        "/app.js",
        SimpleNamespace(
            status=200,
            body=(WEB_ROOT / "app.js").read_bytes(),
            content_type="text/javascript; charset=utf-8",
            headers=(),
        ),
    )
    script = response.body.decode()
    assert 'api("/api/v1/projects")' not in script
    assert 'api("/api/v1/observations")' not in script
    assert "/api/v1/media?limit=500" not in script
    assert "/api/v1/projects?limit=50" in script
    assert "/api/v1/observations?limit=50" in script
    assert "/api/v1/media?limit=50" in script
    assert "projects-load-more" in script
    assert "media-load-more" in script
    assert "observations-load-more" in script
    assert "audit-load-more" in script
