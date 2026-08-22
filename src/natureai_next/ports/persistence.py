"""Persistence ports owned by the application core."""

from __future__ import annotations

from typing import Protocol, Self

from natureai_next.domain.catalog import Asset, Collection, FileInstance, Tag
from natureai_next.domain.events import AuditEntry, OutboxEvent
from natureai_next.domain.jobs import JobRecord


class AssetRepository(Protocol):
    def add(self, asset: Asset) -> Asset: ...
    def get_by_public_id(self, public_id: str) -> Asset | None: ...
    def list_page(self, *, limit: int, after_id: int | None = None) -> tuple[Asset, ...]: ...


class FileInstanceRepository(Protocol):
    def add(self, item: FileInstance) -> FileInstance: ...
    def find_by_sha256(self, sha256: str) -> tuple[FileInstance, ...]: ...


class TagRepository(Protocol):
    def add(self, tag: Tag) -> Tag: ...
    def attach(self, *, asset_id: int, tag_id: int, source: str, created_at_us: int) -> None: ...


class CollectionRepository(Protocol):
    def add(self, collection: Collection) -> Collection: ...
    def add_asset(
        self, *, collection_id: int, asset_id: int, position_key: str, added_at_us: int
    ) -> None: ...


class JobRepository(Protocol):
    def add(self, job: JobRecord) -> JobRecord: ...


class OutboxRepository(Protocol):
    def add(self, event: OutboxEvent) -> OutboxEvent: ...


class AuditRepository(Protocol):
    def add(self, entry: AuditEntry) -> AuditEntry: ...


class UnitOfWork(Protocol):
    assets: AssetRepository
    files: FileInstanceRepository
    tags: TagRepository
    collections: CollectionRepository
    jobs: JobRepository
    outbox: OutboxRepository
    audit: AuditRepository

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
