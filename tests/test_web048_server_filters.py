from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.api import ApiResponse, FieldoraApi, ScienceReadProjection
from natureai_next.server.filtering import FilteringApiMixin, patch_filtering_web_response
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.pagination_api import PaginationApiMixin, patch_pagination_web_response

ROOT = Path(__file__).parents[1]
WEB_ROOT = ROOT / "src/natureai_next/resources/server_web"


class _Authentication:
    identity = Identity("user-1", IdentityKind.USER, "User", "local")

    def authenticate(self, token: str) -> Identity:
        assert token == "filter-token"
        return self.identity


class _Decisions:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def decide(self, request):
        self.seen.append(request.resource_id)
        return SimpleNamespace(allowed="denied" not in request.resource_id)


class _FilteredApi(FilteringApiMixin, PaginationApiMixin, FieldoraApi):
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
        values = (
            ("o-1", "Arctic fox", "confirmed"),
            ("o-denied", "Arctic fox hidden", "confirmed"),
            ("o-2", "Red fox", "disputed"),
            ("o-3", "Arctic tern", "confirmed"),
            ("o-4", "Fox track", "confirmed"),
        )
        for updated_at, (record_id, name, status) in enumerate(values, start=1):
            connection.execute(
                "INSERT INTO science_records VALUES(?,?,?,?,?)",
                (
                    "server_observations",
                    record_id,
                    json.dumps(
                        {
                            "id": record_id,
                            "project_id": "p-1",
                            "name": name,
                            "status": status,
                        }
                    ),
                    1,
                    updated_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return ScienceReadProjection(database)


def _media(tmp_path: Path) -> GovernedMediaStore:
    database = tmp_path / "media.sqlite3"
    store = GovernedMediaStore(database, tmp_path / "objects")
    rows = (
        ("z-photo-fox", "image/jpeg"),
        ("y-photo-fox-denied", "image/jpeg"),
        ("x-audio-fox", "audio/wav"),
        ("w-photo-owl", "image/jpeg"),
        ("v-photo-fox", "image/png"),
    )
    connection = sqlite3.connect(database)
    try:
        for index, (media_id, mime_type) in enumerate(rows, start=1):
            connection.execute(
                "INSERT INTO governed_media VALUES(?,?,?,?,?,?,?)",
                (
                    media_id,
                    None,
                    "local",
                    "p-1",
                    mime_type,
                    10 + index,
                    f"{index:064x}",
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return store


def _api(tmp_path: Path) -> tuple[_FilteredApi, _Decisions]:
    decisions = _Decisions()
    api = _FilteredApi(
        _Authentication(),
        decisions,
        _science(tmp_path),
        WEB_ROOT,
        _media(tmp_path),
    )
    return api, decisions


def _get(api: _FilteredApi, path: str) -> dict:
    response = api.dispatch(
        "GET",
        path,
        {"authorization": "Bearer filter-token"},
        b"",
    )
    assert response.status == 200
    return json.loads(response.body)


def test_web048_library_search_and_kind_filter_run_before_pbac(tmp_path: Path) -> None:
    api, decisions = _api(tmp_path)
    first = _get(api, "/api/v1/media?limit=1&q=fox&kind=image")
    assert [item["media_id"] for item in first["items"]] == ["z-photo-fox"]
    assert first["count"] == 1
    assert first["next_cursor"]
    assert set(decisions.seen) == {
        "z-photo-fox",
        "y-photo-fox-denied",
        "v-photo-fox",
    }
    assert "x-audio-fox" not in decisions.seen
    assert "w-photo-owl" not in decisions.seen

    decisions.seen.clear()
    second = _get(
        api,
        "/api/v1/media?limit=1&q=fox&kind=image&after="
        + quote(first["next_cursor"]),
    )
    assert [item["media_id"] for item in second["items"]] == ["v-photo-fox"]
    assert second["next_cursor"] == ""
    assert decisions.seen == ["y-photo-fox-denied", "v-photo-fox"]


def test_web048_observation_search_and_status_filter_run_before_pbac(tmp_path: Path) -> None:
    api, decisions = _api(tmp_path)
    first = _get(api, "/api/v1/observations?limit=1&q=fox&status=confirmed")
    assert [item["id"] for item in first["items"]] == ["o-1"]
    assert first["next_cursor"]
    assert set(decisions.seen) == {"o-1", "o-denied", "o-4"}
    assert "o-2" not in decisions.seen
    assert "o-3" not in decisions.seen

    decisions.seen.clear()
    second = _get(
        api,
        "/api/v1/observations?limit=1&q=fox&status=confirmed&after="
        + quote(first["next_cursor"]),
    )
    assert [item["id"] for item in second["items"]] == ["o-4"]
    assert second["next_cursor"] == ""
    assert decisions.seen == ["o-denied", "o-4"]


def test_web048_filter_validation_fails_closed(tmp_path: Path) -> None:
    api, _decisions = _api(tmp_path)
    headers = {"authorization": "Bearer filter-token"}
    for path, error in (
        ("/api/v1/media?kind=executable", "invalid_filter"),
        ("/api/v1/observations?status=secret", "invalid_filter"),
        ("/api/v1/media?q=" + "x" * 201, "invalid_query"),
    ):
        response = api.dispatch("GET", path, headers, b"")
        assert response.status == 400
        assert json.loads(response.body) == {"error": error}


def test_web048_managed_client_refetches_filters_instead_of_local_only_render() -> None:
    assert issubclass(OfflineFirstFieldoraApi, FilteringApiMixin)
    base = ApiResponse(
        200,
        (WEB_ROOT / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    response = patch_filtering_web_response(
        "/app.js", patch_pagination_web_response("/app.js", base)
    )
    script = response.body.decode()
    assert 'params.set("q",search)' in script
    assert 'params.set("kind",kind)' in script
    assert 'params.set("status",statusValue)' in script
    assert "loadMedia(true)" in script
    assert "loadObservations(true)" in script
    assert "filteredMediaCursor" in script
    assert "filteredObservationCursor" in script
