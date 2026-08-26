from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest

from natureai_next.server.media import GovernedMediaStore, MediaRecord
from natureai_next.server.media_links import new_association
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


def _assert_one_managed_instance(store: GovernedMediaStore, record: MediaRecord) -> None:
    instances = store.instances(record.media_id, record.organization_id)
    assert len(instances) == 1
    instance = instances[0]
    assert instance.media_id == record.media_id
    assert instance.organization_id == record.organization_id
    assert instance.storage_kind == "managed"
    assert instance.availability == "available"
    assert instance.size_bytes == record.size_bytes
    assert instance.sha256 == record.sha256


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
    _assert_one_managed_instance(store, first)

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM governed_media WHERE organization_id=%s "
                "AND project_id=%s AND sha256=%s AND size_bytes=%s",
                (organization_id, project_id, first.sha256, first.size_bytes),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT count(*) FROM governed_media_instances WHERE media_id=%s "
                "AND organization_id=%s AND storage_kind='managed'",
                (first.media_id, organization_id),
            )
            assert cursor.fetchone()[0] == 1


@pytest.mark.integration
def test_postgres_canonical_media_has_two_project_associations(tmp_path: Path) -> None:
    connect = _connect_factory()
    repository = PostgresMediaMetadataRepository(connect)
    store = GovernedMediaStore(
        tmp_path / "unused-associations.sqlite3",
        tmp_path / "association-objects",
        metadata=repository,
    )
    organization_id = f"org-{uuid4()}"
    project_a = f"project-a-{uuid4()}"
    project_b = f"project-b-{uuid4()}"
    project_c = f"project-c-{uuid4()}"
    payload = b"postgres cross-project canonical governed evidence"

    first = _upload(
        store,
        payload,
        organization_id=organization_id,
        project_id=project_a,
    )
    second = _upload(
        store,
        payload,
        organization_id=organization_id,
        project_id=project_b,
    )

    assert second.media_id == first.media_id
    assert len(store.records(organization_id)) == 1
    _assert_one_managed_instance(store, first)

    for project_id in (project_a, project_b):
        repository.associations.link(
            new_association(
                media_id=first.media_id,
                organization_id=organization_id,
                association_type="project",
                target_id=project_id,
                purpose="research",
                linked_by="subject-1",
            )
        )

    links = repository.associations.links(first.media_id, organization_id)
    assert [link.target_id for link in links] == sorted((project_a, project_b))
    assert repository.associations.linked_media_ids(
        organization_id, "project", project_a
    ) == (first.media_id,)
    assert repository.associations.linked_media_ids(
        organization_id, "project", project_b
    ) == (first.media_id,)
    assert repository.associations.linked_media_ids(
        organization_id, "project", project_c
    ) == ()

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM governed_media WHERE organization_id=%s "
                "AND sha256=%s AND size_bytes=%s",
                (organization_id, first.sha256, first.size_bytes),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT count(*), count(DISTINCT target_id) "
                "FROM governed_media_associations WHERE media_id=%s "
                "AND organization_id=%s AND association_type='project'",
                (first.media_id, organization_id),
            )
            assert cursor.fetchone() == (2, 2)


@pytest.mark.integration
def test_postgres_existing_governed_media_is_backfilled_as_managed(tmp_path: Path) -> None:
    connect = _connect_factory()
    repository = PostgresMediaMetadataRepository(connect)
    store = GovernedMediaStore(
        tmp_path / "unused-backfill.sqlite3",
        tmp_path / "backfill-objects",
        metadata=repository,
    )
    organization_id = f"org-{uuid4()}"
    project_id = f"project-{uuid4()}"
    record = _upload(
        store,
        b"postgres legacy managed evidence",
        organization_id=organization_id,
        project_id=project_id,
    )

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM governed_media_instances WHERE media_id=%s",
                (record.media_id,),
            )

    reloaded_repository = PostgresMediaMetadataRepository(connect)
    reloaded_store = GovernedMediaStore(
        tmp_path / "unused-backfill-reload.sqlite3",
        tmp_path / "backfill-reload-objects",
        metadata=reloaded_repository,
    )

    _assert_one_managed_instance(reloaded_store, record)
