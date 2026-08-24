from __future__ import annotations

import os
from uuid import uuid4

import pytest

from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.storage_exchange import StorageSourceRegistration


def _repository() -> PostgresLinkedStorageRepository:
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return PostgresLinkedStorageRepository(lambda: psycopg.connect(dsn))


@pytest.mark.integration
def test_linked_archive_lifecycle_is_actor_audited_and_idempotent() -> None:
    repository = _repository()
    suffix = uuid4().hex
    source = StorageSourceRegistration(
        storage_id=f"storage-{suffix}",
        organization_id=f"org-{suffix}",
        service_id=f"service-{suffix}",
        display_name="Lifecycle archive",
        root_alias=f"archive-{suffix}",
        read_only=True,
    )
    repository.register_source(source)

    assert repository.set_source_enabled(
        source.storage_id,
        source.organization_id,
        False,
        actor_id="operator-1",
    )
    assert repository.source(source.storage_id) is None
    assert repository.set_source_enabled(
        source.storage_id,
        source.organization_id,
        False,
        actor_id="operator-1",
    )
    assert repository.set_source_enabled(
        source.storage_id,
        source.organization_id,
        True,
        actor_id="operator-2",
    )
    assert repository.source(source.storage_id) is not None

    with repository.connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT actor_id,event_type FROM linked_storage_source_events_pg "
                "WHERE storage_id=%s AND organization_id=%s ORDER BY sequence",
                (source.storage_id, source.organization_id),
            )
            events = cursor.fetchall()

    assert events == [
        ("operator-1", "source_disabled"),
        ("operator-2", "source_enabled"),
    ]


@pytest.mark.integration
def test_linked_archive_lifecycle_cannot_cross_organization_boundary() -> None:
    repository = _repository()
    suffix = uuid4().hex
    source = StorageSourceRegistration(
        storage_id=f"storage-{suffix}",
        organization_id=f"org-{suffix}",
        service_id=f"service-{suffix}",
        display_name="Scoped archive",
        root_alias=f"archive-{suffix}",
        read_only=True,
    )
    repository.register_source(source)

    assert not repository.set_source_enabled(
        source.storage_id,
        "other-organization",
        False,
        actor_id="operator-foreign",
    )
    assert repository.source(source.storage_id) is not None

    with repository.connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM linked_storage_source_events_pg WHERE storage_id=%s",
                (source.storage_id,),
            )
            assert int(cursor.fetchone()[0]) == 0
