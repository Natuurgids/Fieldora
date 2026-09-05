from __future__ import annotations

import os
from dataclasses import replace
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


def _events(
    repository: PostgresLinkedStorageRepository,
    source: StorageSourceRegistration,
) -> list[tuple[str, str]]:
    with repository.connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT actor_id,event_type FROM linked_storage_source_events_pg "
                "WHERE storage_id=%s AND organization_id=%s ORDER BY sequence",
                (source.storage_id, source.organization_id),
            )
            return list(cursor.fetchall())


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
    repository.register_source(source)

    assert repository.set_source_enabled(
        source.storage_id,
        source.organization_id,
        False,
        actor_id="operator-1",
    )
    assert repository.source(source.storage_id) is None

    repository.register_source(source)
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

    updated = replace(source, display_name="Renamed lifecycle archive")
    repository.register_source(updated)
    repository.register_source(updated)

    assert _events(repository, source) == [
        (source.service_id, "source_registered"),
        ("operator-1", "source_disabled"),
        ("operator-2", "source_enabled"),
        (source.service_id, "source_registration_updated"),
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
    assert _events(repository, source) == [(source.service_id, "source_registered")]
