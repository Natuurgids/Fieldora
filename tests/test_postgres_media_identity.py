from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest

from natureai_next.server.media import GovernedMediaStore, MediaRecord
from natureai_next.server.postgres_media import PostgresMediaMetadataRepository


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


def _upload(
    store: GovernedMediaStore,
    payload: bytes,
    *,
    organization_id: str,
    project_id: str,
) -> MediaRecord:
    digest = hashlib.sha256(payload).hexdigest()
    upload = store.begin_upload(
        "subject-1",
        organization_id,
        project_id,
        "evidence.bin",
        "application/octet-stream",
        len(payload),
        digest,
    )
    result = store.append_upload(upload, 0, payload)
    assert isinstance(result, MediaRecord)
    return result


@pytest.mark.integration
def test_postgres_repeated_upload_returns_canonical_media_identity(tmp_path: Path) -> None:
    connect = _connect_factory()
    repository = PostgresMediaMetadataRepository(connect)
    store = GovernedMediaStore(
        tmp_path / "unused.sqlite3",
        tmp_path / "objects",
        metadata=repository,
    )
    organization_id = f"org-{uuid4()}"
    project_id = f"project-{uuid4()}"
    payload = b"postgres canonical governed evidence"

    first = _upload(
        store,
        payload,
        organization_id=organization_id,
        project_id=project_id,
    )
    repeated = _upload(
        store,
        payload,
        organization_id=organization_id,
        project_id=project_id,
    )

    assert repeated.media_id == first.media_id
    assert repeated.relative_path == first.relative_path
    assert store.records(organization_id, project_id) == (first,)

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM governed_media WHERE organization_id=%s "
                "AND project_id=%s AND sha256=%s AND size_bytes=%s",
                (organization_id, project_id, first.sha256, first.size_bytes),
            )
            assert cursor.fetchone()[0] == 1
