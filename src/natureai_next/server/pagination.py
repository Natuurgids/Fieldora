"""Bounded keyset pagination adapters for managed web list projections.

The web API needs stable pages without changing the authoritative write services.  These
helpers keep pagination at the existing persistence boundaries: SQLite/PostgreSQL
Science, managed PostgreSQL Projects, governed media metadata, and access audit rows.
Cursors are opaque transport values and never contain authorization decisions or counts.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from natureai_next.server.media import MediaRecord


def _cursor(kind: str, *values: object) -> str:
    payload = json.dumps([kind, *values], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode(value: str, kind: str, size: int) -> tuple[object, ...]:
    if not value:
        return ()
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != size + 1
        or decoded[0] != kind
    ):
        raise ValueError("invalid_cursor")
    return tuple(decoded[1:])


def _payload(value: object) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("science payload must be an object")
    return dict(parsed)


def _sqlite_science_page(
    database_path: Any, collection: str, after: str, limit: int
) -> tuple[tuple[dict, str], ...]:
    position = _decode(after, f"science:{collection}", 2)
    connection = sqlite3.connect(database_path)
    try:
        if position:
            updated_at_us, record_id = int(position[0]), str(position[1])
            rows = connection.execute(
                "SELECT payload_json,updated_at_us,record_id FROM science_records "
                "WHERE collection_name=? AND "
                "(updated_at_us>? OR (updated_at_us=? AND record_id>?)) "
                "ORDER BY updated_at_us,record_id LIMIT ?",
                (collection, updated_at_us, updated_at_us, record_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT payload_json,updated_at_us,record_id FROM science_records "
                "WHERE collection_name=? ORDER BY updated_at_us,record_id LIMIT ?",
                (collection, limit),
            ).fetchall()
    finally:
        connection.close()
    return tuple(
        (
            _payload(row[0]),
            _cursor(f"science:{collection}", int(row[1]), str(row[2])),
        )
        for row in rows
    )


def scan_science(
    science: object, collection: str, after: str, limit: int
) -> tuple[tuple[dict, str], ...]:
    """Return one bounded persistence page in deterministic Science order."""
    limit = max(1, min(int(limit), 200))
    database_path = getattr(science, "_database_path", None)
    if database_path is not None:
        if not database_path.is_file():
            return ()
        return _sqlite_science_page(database_path, collection, after, limit)

    connect = getattr(science, "_connect", None)
    if connect is not None:
        position = _decode(after, f"science:{collection}", 2)
        with connect() as connection:
            with connection.cursor() as cursor:
                if position:
                    updated_at_us, record_id = int(position[0]), str(position[1])
                    cursor.execute(
                        "SELECT payload_json,updated_at_us,record_id FROM science_records "
                        "WHERE collection_name=%s AND "
                        "(updated_at_us>%s OR (updated_at_us=%s AND record_id>%s)) "
                        "ORDER BY updated_at_us,record_id LIMIT %s",
                        (collection, updated_at_us, updated_at_us, record_id, limit),
                    )
                else:
                    cursor.execute(
                        "SELECT payload_json,updated_at_us,record_id FROM science_records "
                        "WHERE collection_name=%s ORDER BY updated_at_us,record_id LIMIT %s",
                        (collection, limit),
                    )
                rows = cursor.fetchall()
        return tuple(
            (
                _payload(row[0]),
                _cursor(f"science:{collection}", int(row[1]), str(row[2])),
            )
            for row in rows
        )

    # Compatibility for narrow unit fakes. Production adapters take the bounded paths above.
    records = tuple(getattr(science, "records")(collection))
    position = _decode(after, f"science-fallback:{collection}", 1)
    offset = int(position[0]) if position else 0
    return tuple(
        (record, _cursor(f"science-fallback:{collection}", index + 1))
        for index, record in enumerate(records[offset : offset + limit], start=offset)
    )


def scan_projects(
    service: object, organization_id: str, after: str, limit: int
) -> tuple[tuple[dict[str, object], str], ...]:
    """Return a bounded managed-Project page in the service's established order."""
    limit = max(1, min(int(limit), 200))
    connect = getattr(service, "_connect", None)
    if connect is None:
        projects = tuple(getattr(service, "projects")(organization_id))
        position = _decode(after, "projects-fallback", 1)
        offset = int(position[0]) if position else 0
        return tuple(
            (
                _project_payload(project),
                _cursor("projects-fallback", index + 1),
            )
            for index, project in enumerate(
                projects[offset : offset + limit], start=offset
            )
        )

    position = _decode(after, "projects", 2)
    with connect() as connection:
        with connection.cursor() as cursor:
            if position:
                updated_at_us, project_id = int(position[0]), str(position[1])
                cursor.execute(
                    "SELECT project_id,organization_id,name,status,owner_id,start_date,"
                    "due_date,budget,currency,description,updated_at_us FROM pm_projects "
                    "WHERE organization_id=%s AND "
                    "(updated_at_us<%s OR (updated_at_us=%s AND project_id>%s)) "
                    "ORDER BY updated_at_us DESC,project_id LIMIT %s",
                    (
                        organization_id,
                        updated_at_us,
                        updated_at_us,
                        project_id,
                        limit,
                    ),
                )
            else:
                cursor.execute(
                    "SELECT project_id,organization_id,name,status,owner_id,start_date,"
                    "due_date,budget,currency,description,updated_at_us FROM pm_projects "
                    "WHERE organization_id=%s ORDER BY updated_at_us DESC,project_id LIMIT %s",
                    (organization_id, limit),
                )
            rows = cursor.fetchall()
    return tuple(
        (
            {
                "id": str(row[0]),
                "name": str(row[2]),
                "status": str(row[3]),
                "owner_id": str(row[4]),
                "start_date": str(row[5]),
                "due_date": str(row[6]),
                "budget": float(row[7]),
                "currency": str(row[8]),
                "description": str(row[9]),
                "revision": int(row[10]),
            },
            _cursor("projects", int(row[10]), str(row[0])),
        )
        for row in rows
    )


def _project_payload(project: object) -> dict[str, object]:
    return {
        "id": str(getattr(project, "project_id")),
        "name": str(getattr(project, "name")),
        "description": str(getattr(project, "description", "")),
        "status": str(getattr(project, "status", "")),
        "owner_id": str(getattr(project, "owner_id", "")),
        "start_date": str(getattr(project, "start_date", "")),
        "due_date": str(getattr(project, "due_date", "")),
        "budget": float(getattr(project, "budget", 0)),
        "currency": str(getattr(project, "currency", "EUR")),
        "revision": int(getattr(project, "revision", 0)),
    }


def scan_media(
    store: object,
    organization_id: str,
    project_id: str,
    after: str,
    limit: int,
) -> tuple[tuple[MediaRecord, str], ...]:
    """Return a bounded governed-media page ordered by descending canonical ID."""
    limit = max(1, min(int(limit), 200))
    position = _decode(after, "media", 1)
    media_id = str(position[0]) if position else ""
    metadata = getattr(store, "_metadata", None)
    connect = None if metadata is None else getattr(metadata, "_connect", None)
    if connect is not None:
        clauses = ["organization_id=%s"]
        params: list[object] = [organization_id]
        if project_id:
            clauses.append("project_id=%s")
            params.append(project_id)
        if media_id:
            clauses.append("media_id<%s")
            params.append(media_id)
        params.append(limit)
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,relative_path,organization_id,project_id,mime_type,"
                    "size_bytes,sha256 FROM governed_media WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY media_id DESC LIMIT %s",
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(
            (MediaRecord(*row), _cursor("media", str(row[0]))) for row in rows
        )

    database_path = getattr(store, "_database_path", None)
    if database_path is not None:
        connection = sqlite3.connect(database_path)
        try:
            clauses = ["organization_id=?"]
            params = [organization_id]
            if project_id:
                clauses.append("project_id=?")
                params.append(project_id)
            if media_id:
                clauses.append("media_id<?")
                params.append(media_id)
            params.append(limit)
            rows = connection.execute(
                "SELECT * FROM governed_media WHERE "
                + " AND ".join(clauses)
                + " ORDER BY media_id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            (MediaRecord(*row), _cursor("media", str(row[0]))) for row in rows
        )

    records = tuple(getattr(store, "records")(organization_id, project_id, limit))
    return tuple((record, _cursor("media", record.media_id)) for record in records)


def scan_audit(
    repository: object, after: str, limit: int
) -> tuple[tuple[Mapping[str, Any], str], ...]:
    """Return bounded audit rows newest first without exposing a total."""
    limit = max(1, min(int(limit), 200))
    position = _decode(after, "audit", 1)
    sequence = int(position[0]) if position else 0
    factory = getattr(repository, "_factory", None)
    if factory is None:
        events = tuple(getattr(repository, "audit_events")(limit=limit))
        return tuple(
            (event, _cursor("audit", int(event["sequence"]))) for event in events
        )
    connection = factory.connect(read_only=True)
    try:
        if sequence:
            rows = connection.execute(
                "SELECT * FROM access_audit_events WHERE sequence<? "
                "ORDER BY sequence DESC LIMIT ?",
                (sequence, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM access_audit_events ORDER BY sequence DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        connection.close()
    return tuple(
        (row, _cursor("audit", int(row["sequence"]))) for row in rows
    )
