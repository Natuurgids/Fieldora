"""Rebuildable FTS projection whose candidates require PBAC before disclosure."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class SearchHit:
    resource_type: str
    resource_id: str
    organization_id: str
    project_id: str
    title: str
    snippet: str


class SearchProjection(Protocol):
    def rebuild(
        self, science_source: Path | ScienceRecordSource, organization_id: str
    ) -> int: ...

    def candidates(self, query: str, limit: int) -> tuple[SearchHit, ...]: ...


class ScienceRecordSource(Protocol):
    def records(self, collection: str) -> tuple[dict, ...]: ...


def _science_documents(
    science_source: Path | ScienceRecordSource, organization_id: str
) -> list[tuple[str, str, str, str, str, str]]:
    records: list[tuple[str, str, str, str, str, str]] = []
    rows = []
    searchable_collections = {
        "projects": "project",
        "dossiers": "dossier",
        "server_observations": "observation",
        "server_knowledge": "knowledge",
        "server_collections": "collection",
    }
    if isinstance(science_source, Path):
        if not science_source.is_file():
            return records
        source = sqlite3.connect(science_source)
        try:
            rows = source.execute(
                "SELECT collection_name,record_id,payload_json FROM science_records "
                "WHERE collection_name IN "
                "('projects','dossiers','server_observations',"
                "'server_knowledge','server_collections') "
                "ORDER BY collection_name,record_id"
            ).fetchall()
        finally:
            source.close()
    else:
        rows = [
            (collection, str(record["id"]), json.dumps(record))
            for collection in searchable_collections
            for record in science_source.records(collection)
        ]
    for collection, record_id, payload_json in rows:
        payload = json.loads(str(payload_json))
        resource_type = searchable_collections.get(str(collection))
        if resource_type is None:
            continue
        project_id = (
            str(record_id) if resource_type == "project"
            else str(payload.get("project_id", ""))
        )
        title = str(payload.get("title") or payload.get("name") or record_id)
        records.append(
            (
                resource_type, str(record_id), organization_id, project_id,
                title, json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
        )
    return records


class ServerSearchProjection:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_documents(
                    row_id INTEGER PRIMARY KEY,resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,
                    UNIQUE(resource_type,resource_id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                    title,body,content='search_documents',content_rowid='row_id'
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def rebuild(
        self, science_source: Path | ScienceRecordSource, organization_id: str
    ) -> int:
        records = _science_documents(science_source, organization_id)
        connection = sqlite3.connect(self._database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM search_documents")
            connection.executemany(
                "INSERT INTO search_documents(resource_type,resource_id,organization_id,"
                "project_id,title,body) VALUES(?,?,?,?,?,?)",
                records,
            )
            connection.execute("INSERT INTO search_fts(search_fts) VALUES('rebuild')")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return len(records)

    def candidates(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        terms = re.findall(r"\w+", query, flags=re.UNICODE)[:10]
        if not terms:
            return ()
        expression = " AND ".join(f'"{term}"*' for term in terms)
        connection = sqlite3.connect(self._database_path)
        try:
            rows = connection.execute(
                "SELECT d.resource_type,d.resource_id,d.organization_id,d.project_id,"
                "d.title,snippet(search_fts,1,'[',']',' … ',18) "
                "FROM search_fts JOIN search_documents d ON d.row_id=search_fts.rowid "
                "WHERE search_fts MATCH ? ORDER BY bm25(search_fts),d.row_id LIMIT ?",
                (expression, max(1, min(limit, 500))),
            ).fetchall()
        finally:
            connection.close()
        return tuple(SearchHit(*row) for row in rows)


class OpenSearchProjection:
    """Rebuildable HTTPS OpenSearch projection behind the PBAC candidate boundary."""

    def __init__(
        self,
        endpoint: str,
        index_alias: str = "fieldora-search",
        timeout_seconds: float = 10.0,
        request_json: Callable[[str, str, dict | None, int], dict] | None = None,
        bearer_token: str = "",
    ) -> None:
        parsed = urlsplit(endpoint.rstrip("/"))
        if (
            parsed.scheme != "https" or not parsed.netloc
            or parsed.username is not None or parsed.password is not None
        ):
            raise ValueError("OpenSearch endpoint must be an absolute HTTPS URL")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("OpenSearch endpoint must not contain a path or query")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", index_alias):
            raise ValueError("OpenSearch index alias is invalid")
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("OpenSearch timeout must be between 1 and 60 seconds")
        self._endpoint = endpoint.rstrip("/")
        self._origin = (parsed.scheme, parsed.netloc)
        self._index_alias = index_alias
        self._timeout_seconds = timeout_seconds
        self._request_json = request_json or self._download_json
        self._bearer_token = bearer_token

    def rebuild(
        self, science_source: Path | ScienceRecordSource, organization_id: str
    ) -> int:
        records = _science_documents(science_source, organization_id)
        concrete = f"{self._index_alias}-{uuid4().hex}"
        mapping = {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "resource_type": {"type": "keyword"},
                    "resource_id": {"type": "keyword"},
                    "organization_id": {"type": "keyword"},
                    "project_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "body": {"type": "text"},
                },
            }
        }
        self._call("PUT", f"/{quote(concrete)}", mapping)
        if records:
            operations = []
            for item in records:
                document_id = f"{item[0]}:{item[1]}"
                operations.extend(
                    (
                        {"index": {"_index": concrete, "_id": document_id}},
                        {
                            "resource_type": item[0],
                            "resource_id": item[1],
                            "organization_id": item[2],
                            "project_id": item[3],
                            "title": item[4],
                            "body": item[5],
                        },
                    )
                )
            result = self._call("POST", "/_bulk?refresh=true", {"items": operations})
            if result.get("errors") is True:
                raise RuntimeError("OpenSearch bulk indexing failed")
        aliases = self._call("GET", f"/_alias/{quote(self._index_alias)}", None)
        actions = [
            {"remove": {"index": name, "alias": self._index_alias}}
            for name in sorted(aliases)
            if isinstance(name, str)
        ]
        actions.append({"add": {"index": concrete, "alias": self._index_alias}})
        self._call("POST", "/_aliases", {"actions": actions})
        for name in sorted(aliases):
            if (
                isinstance(name, str)
                and name.startswith(f"{self._index_alias}-")
                and name != concrete
            ):
                self._call("DELETE", f"/{quote(name)}", None)
        return len(records)

    def candidates(self, query: str, limit: int) -> tuple[SearchHit, ...]:
        terms = re.findall(r"\w+", query, flags=re.UNICODE)[:10]
        if not terms:
            return ()
        size = max(1, min(limit, 500))
        result = self._call(
            "POST",
            f"/{quote(self._index_alias)}/_search",
            {
                "size": size,
                "_source": [
                    "resource_type", "resource_id", "organization_id",
                    "project_id", "title", "body",
                ],
                "query": {
                    "multi_match": {
                        "query": " ".join(terms),
                        "fields": ["title^3", "body"],
                        "operator": "and",
                    }
                },
            },
        )
        raw_hits = result.get("hits", {}).get("hits", [])
        if not isinstance(raw_hits, list):
            raise RuntimeError("OpenSearch returned invalid hits")
        hits = []
        for raw in raw_hits[:size]:
            source = raw.get("_source", {}) if isinstance(raw, dict) else {}
            if not isinstance(source, dict):
                raise RuntimeError("OpenSearch returned an invalid document")
            values = tuple(
                source.get(name)
                for name in (
                    "resource_type", "resource_id", "organization_id",
                    "project_id", "title",
                )
            )
            if not all(isinstance(value, str) for value in values):
                raise RuntimeError("OpenSearch document metadata is invalid")
            body = source.get("body", "")
            snippet = str(body)[:240] if isinstance(body, str) else ""
            hits.append(SearchHit(*values, snippet))
        return tuple(hits)

    def ready(self) -> bool:
        result = self._call("GET", "/_cluster/health", None)
        return result.get("status") in {"green", "yellow"}

    def _call(self, method: str, path: str, body: dict | None) -> dict:
        return self._request_json(method, self._endpoint + path, body, 2 * 1024 * 1024)

    def _download_json(
        self, method: str, url: str, body: dict | None, maximum_bytes: int
    ) -> dict:
        content_type = "application/json"
        if url.endswith("/_bulk?refresh=true") and body is not None:
            payload = (
                "\n".join(json.dumps(item, separators=(",", ":")) for item in body["items"])
                + "\n"
            ).encode("utf-8")
            content_type = "application/x-ndjson"
        else:
            payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        request = Request(url, data=payload, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                final = urlsplit(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    raise ValueError(
                        "OpenSearch redirect left the configured HTTPS origin"
                    )
                raw = response.read(maximum_bytes + 1)
        except HTTPError as exc:
            if method == "GET" and "/_alias/" in url and exc.code == 404:
                return {}
            raise
        if len(raw) > maximum_bytes:
            raise ValueError("OpenSearch response is too large")
        document = json.loads(raw or b"{}")
        if not isinstance(document, dict):
            raise ValueError("OpenSearch response must be a JSON object")
        return document
