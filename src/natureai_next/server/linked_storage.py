"""Offline-first linked scientific storage catalogue and preview scheduling.

Fieldora owns governance, identity, provenance and relationships; the original bytes
may remain on an organisation-controlled filesystem.  This module deliberately has
no network dependency.  Files are addressed by a configured storage source plus a
normalised relative path and are read only through the governed storage service.
"""

from __future__ import annotations

import hashlib
import heapq
import mimetypes
import os
import sqlite3
import time
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from threading import RLock
from uuid import uuid4

from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class LinkedStorageSource:
    storage_id: str
    organization_id: str
    name: str
    root_path: str
    enabled: bool = True
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class LinkedMediaRecord:
    media_id: str
    storage_id: str
    organization_id: str
    project_id: str
    relative_path: str
    mime_type: str
    size_bytes: int
    modified_ns: int
    sha256: str = ""
    thumbnail_state: str = "pending"
    thumbnail_key: str = ""
    preview_state: str = "pending"
    missing: bool = False


@dataclass(frozen=True, slots=True)
class CatalogueCheckpoint:
    scan_id: str
    storage_id: str
    relative_root: str
    discovered: int
    registered: int
    errors: int
    last_relative_path: str
    state: str
    updated_at_epoch: int


@dataclass(frozen=True, slots=True)
class PreviewRequest:
    media_id: str
    priority: int
    requested_at_epoch: int
    reason: str


class LinkedStorageRepository:
    """SQLite repository for standalone/testing deployments.

    The schema is intentionally adapter-friendly so the PostgreSQL implementation can
    use the same records in managed deployments.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS linked_storage_sources(
                    storage_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    read_only INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS linked_media(
                    media_id TEXT PRIMARY KEY,
                    storage_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    thumbnail_state TEXT NOT NULL,
                    thumbnail_key TEXT NOT NULL,
                    preview_state TEXT NOT NULL,
                    missing INTEGER NOT NULL,
                    UNIQUE(storage_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS ix_linked_media_storage_path
                    ON linked_media(storage_id,relative_path);
                CREATE INDEX IF NOT EXISTS ix_linked_media_org_project
                    ON linked_media(organization_id,project_id,media_id);
                CREATE TABLE IF NOT EXISTS linked_catalogue_checkpoints(
                    scan_id TEXT PRIMARY KEY,
                    storage_id TEXT NOT NULL,
                    relative_root TEXT NOT NULL,
                    discovered INTEGER NOT NULL,
                    registered INTEGER NOT NULL,
                    errors INTEGER NOT NULL,
                    last_relative_path TEXT NOT NULL,
                    state TEXT NOT NULL,
                    updated_at_epoch INTEGER NOT NULL
                );
                """
            )

    def put_source(self, source: LinkedStorageSource) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "INSERT INTO linked_storage_sources VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(storage_id) DO UPDATE SET organization_id=excluded.organization_id,"
                "name=excluded.name,root_path=excluded.root_path,enabled=excluded.enabled,"
                "read_only=excluded.read_only",
                (
                    source.storage_id,
                    source.organization_id,
                    source.name,
                    source.root_path,
                    int(source.enabled),
                    int(source.read_only),
                ),
            )

    def source(self, storage_id: str) -> LinkedStorageSource | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT storage_id,organization_id,name,root_path,enabled,read_only "
                "FROM linked_storage_sources WHERE storage_id=?",
                (storage_id,),
            ).fetchone()
        if row is None:
            return None
        return LinkedStorageSource(
            str(row[0]), str(row[1]), str(row[2]), str(row[3]), bool(row[4]), bool(row[5])
        )

    def sources(self, organization_id: str) -> tuple[LinkedStorageSource, ...]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                "SELECT storage_id,organization_id,name,root_path,enabled,read_only "
                "FROM linked_storage_sources WHERE organization_id=? ORDER BY name,storage_id",
                (organization_id,),
            ).fetchall()
        return tuple(
            LinkedStorageSource(
                str(row[0]), str(row[1]), str(row[2]), str(row[3]), bool(row[4]), bool(row[5])
            )
            for row in rows
        )

    def upsert_media(self, record: LinkedMediaRecord) -> LinkedMediaRecord:
        with sqlite3.connect(self._database_path) as connection:
            existing = connection.execute(
                "SELECT media_id,sha256,thumbnail_state,thumbnail_key,preview_state "
                "FROM linked_media WHERE storage_id=? AND relative_path=?",
                (record.storage_id, record.relative_path),
            ).fetchone()
            media_id = record.media_id if existing is None else str(existing[0])
            sha256 = record.sha256 if existing is None else str(existing[1])
            thumbnail_state = record.thumbnail_state if existing is None else str(existing[2])
            thumbnail_key = record.thumbnail_key if existing is None else str(existing[3])
            preview_state = record.preview_state if existing is None else str(existing[4])
            connection.execute(
                "INSERT INTO linked_media VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(storage_id,relative_path) DO UPDATE SET "
                "organization_id=excluded.organization_id,project_id=excluded.project_id,"
                "mime_type=excluded.mime_type,size_bytes=excluded.size_bytes,"
                "modified_ns=excluded.modified_ns,missing=0",
                (
                    media_id,
                    record.storage_id,
                    record.organization_id,
                    record.project_id,
                    record.relative_path,
                    record.mime_type,
                    record.size_bytes,
                    record.modified_ns,
                    sha256,
                    thumbnail_state,
                    thumbnail_key,
                    preview_state,
                    0,
                ),
            )
        return self.media(media_id) or record

    def media(self, media_id: str) -> LinkedMediaRecord | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT media_id,storage_id,organization_id,project_id,relative_path,"
                "mime_type,size_bytes,modified_ns,sha256,thumbnail_state,thumbnail_key,"
                "preview_state,missing FROM linked_media WHERE media_id=?",
                (media_id,),
            ).fetchone()
        return None if row is None else _decode_media(row)

    def media_in_path(
        self, storage_id: str, relative_root: str = "", limit: int = 500
    ) -> tuple[LinkedMediaRecord, ...]:
        prefix = _normalise_relative(relative_root)
        like = f"{prefix}/%" if prefix else "%"
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                "SELECT media_id,storage_id,organization_id,project_id,relative_path,"
                "mime_type,size_bytes,modified_ns,sha256,thumbnail_state,thumbnail_key,"
                "preview_state,missing FROM linked_media "
                "WHERE storage_id=? AND relative_path LIKE ? AND missing=0 "
                "ORDER BY relative_path LIMIT ?",
                (storage_id, like, max(1, min(int(limit), 5000))),
            ).fetchall()
        return tuple(_decode_media(row) for row in rows)

    def set_thumbnail(self, media_id: str, state: str, key: str = "") -> None:
        if state not in {"pending", "working", "ready", "unsupported", "failed"}:
            raise ValueError("invalid thumbnail state")
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "UPDATE linked_media SET thumbnail_state=?,thumbnail_key=? WHERE media_id=?",
                (state, key, media_id),
            )

    def set_sha256(self, media_id: str, digest: str) -> None:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid sha256")
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "UPDATE linked_media SET sha256=? WHERE media_id=?", (digest, media_id)
            )

    def checkpoint(self, checkpoint: CatalogueCheckpoint) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "INSERT INTO linked_catalogue_checkpoints VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(scan_id) DO UPDATE SET discovered=excluded.discovered,"
                "registered=excluded.registered,errors=excluded.errors,"
                "last_relative_path=excluded.last_relative_path,state=excluded.state,"
                "updated_at_epoch=excluded.updated_at_epoch",
                tuple(asdict(checkpoint).values()),
            )

    def scan(self, scan_id: str) -> CatalogueCheckpoint | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT scan_id,storage_id,relative_root,discovered,registered,errors,"
                "last_relative_path,state,updated_at_epoch FROM linked_catalogue_checkpoints "
                "WHERE scan_id=?",
                (scan_id,),
            ).fetchone()
        return None if row is None else CatalogueCheckpoint(*row)


class LinkedStorageCatalogue:
    """Incremental catalogue that never moves originals and checkpoints continuously."""

    def __init__(self, repository: LinkedStorageRepository) -> None:
        self._repository = repository

    def scan(
        self,
        storage_id: str,
        *,
        relative_root: str = "",
        project_id: str = "",
        scan_id: str | None = None,
        batch_size: int = 250,
    ) -> Iterator[CatalogueCheckpoint]:
        source = self._repository.source(storage_id)
        if source is None or not source.enabled:
            raise ValueError("linked storage source is unavailable")
        root = Path(source.root_path).resolve(strict=True)
        relative_root = _normalise_relative(relative_root)
        scan_root = _contained(root, relative_root)
        current_scan = scan_id or str(uuid4())
        previous = self._repository.scan(current_scan)
        resume_after = "" if previous is None else previous.last_relative_path
        discovered = 0 if previous is None else previous.discovered
        registered = 0 if previous is None else previous.registered
        errors = 0 if previous is None else previous.errors
        pending = 0
        for path in _walk_files(scan_root):
            relative = path.relative_to(root).as_posix()
            if resume_after and relative <= resume_after:
                continue
            discovered += 1
            try:
                stat = path.stat()
                record = LinkedMediaRecord(
                    media_id=str(uuid4()),
                    storage_id=storage_id,
                    organization_id=source.organization_id,
                    project_id=project_id,
                    relative_path=relative,
                    mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    size_bytes=int(stat.st_size),
                    modified_ns=int(stat.st_mtime_ns),
                )
                self._repository.upsert_media(record)
                registered += 1
            except (OSError, ValueError):
                errors += 1
            pending += 1
            if pending >= max(1, batch_size):
                checkpoint = CatalogueCheckpoint(
                    current_scan,
                    storage_id,
                    relative_root,
                    discovered,
                    registered,
                    errors,
                    relative,
                    "running",
                    int(time.time()),
                )
                self._repository.checkpoint(checkpoint)
                yield checkpoint
                pending = 0
        final = CatalogueCheckpoint(
            current_scan,
            storage_id,
            relative_root,
            discovered,
            registered,
            errors,
            "" if discovered == 0 else relative,
            "completed",
            int(time.time()),
        )
        self._repository.checkpoint(final)
        yield final


class PreviewPriorityQueue:
    """Bounded, deduplicated priority queue for interactive/background previews."""

    INTERACTIVE = 0
    VISIBLE_DIRECTORY = 10
    BACKGROUND = 100

    def __init__(self, maximum: int = 100_000) -> None:
        self._maximum = max(1, maximum)
        self._heap: list[tuple[int, int, str, str]] = []
        self._queued: dict[str, tuple[int, int, str]] = {}
        self._counter = 0
        self._lock = RLock()

    def request(self, media_id: str, priority: int, reason: str) -> bool:
        with self._lock:
            existing = self._queued.get(media_id)
            if existing is not None and existing[0] <= priority:
                return False
            if existing is None and len(self._queued) >= self._maximum:
                return False
            self._counter += 1
            self._queued[media_id] = (priority, self._counter, reason[:120])
            heapq.heappush(self._heap, (priority, self._counter, media_id, reason[:120]))
            return True

    def request_visible(self, records: Iterable[LinkedMediaRecord]) -> int:
        return sum(
            self.request(record.media_id, self.VISIBLE_DIRECTORY, "visible-directory")
            for record in records
            if record.thumbnail_state not in {"ready", "unsupported"}
        )

    def pop(self) -> PreviewRequest | None:
        with self._lock:
            while self._heap:
                priority, counter, media_id, reason = heapq.heappop(self._heap)
                current = self._queued.get(media_id)
                if current != (priority, counter, reason):
                    continue
                del self._queued[media_id]
                return PreviewRequest(media_id, priority, int(time.time()), reason)
        return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._queued)


class LinkedPreviewWorker:
    """Generate governed thumbnails in managed preview storage.

    The preview is a performance derivative.  It never replaces or modifies the
    original linked evidence.
    """

    def __init__(
        self,
        repository: LinkedStorageRepository,
        preview_root: Path,
        queue: PreviewPriorityQueue,
        maximum_edge: int = 512,
    ) -> None:
        self._repository = repository
        self._preview_root = preview_root.resolve()
        self._preview_root.mkdir(parents=True, exist_ok=True)
        self._queue = queue
        self._maximum_edge = max(64, min(maximum_edge, 2048))

    def run_one(self) -> LinkedMediaRecord | None:
        request = self._queue.pop()
        if request is None:
            return None
        record = self._repository.media(request.media_id)
        if record is None or record.missing:
            return None
        source = self._repository.source(record.storage_id)
        if source is None or not source.enabled:
            self._repository.set_thumbnail(record.media_id, "failed")
            return self._repository.media(record.media_id)
        if not record.mime_type.startswith("image/"):
            self._repository.set_thumbnail(record.media_id, "unsupported")
            return self._repository.media(record.media_id)
        self._repository.set_thumbnail(record.media_id, "working")
        original = _contained(Path(source.root_path).resolve(strict=True), record.relative_path)
        key = f"{record.media_id[:2]}/{record.media_id}.jpg"
        destination = _contained(self._preview_root, key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(original) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((self._maximum_edge, self._maximum_edge))
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.save(destination, "JPEG", quality=82, optimize=True)
            self._repository.set_thumbnail(record.media_id, "ready", key)
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)
            self._repository.set_thumbnail(record.media_id, "failed")
        return self._repository.media(record.media_id)


def sha256_linked_file(source: LinkedStorageSource, relative_path: str) -> str:
    """Progressively establish a cryptographic integrity digest without moving bytes."""
    root = Path(source.root_path).resolve(strict=True)
    path = _contained(root, relative_path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_files(root: Path) -> Iterator[Path]:
    """Stable traversal makes checkpoint/resume deterministic."""
    for directory, directories, filenames in os.walk(root):
        directories.sort()
        filenames.sort()
        for filename in filenames:
            yield Path(directory) / filename


def _normalise_relative(value: str) -> str:
    raw = value.replace("\\", "/").strip("/")
    if not raw:
        return ""
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("linked path escapes storage source")
    return path.as_posix()


def _contained(root: Path, relative_path: str) -> Path:
    relative = _normalise_relative(relative_path)
    candidate = (root / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("linked path escapes storage source") from exc
    return candidate


def _decode_media(row: tuple[object, ...]) -> LinkedMediaRecord:
    return LinkedMediaRecord(
        media_id=str(row[0]),
        storage_id=str(row[1]),
        organization_id=str(row[2]),
        project_id=str(row[3]),
        relative_path=str(row[4]),
        mime_type=str(row[5]),
        size_bytes=int(row[6]),
        modified_ns=int(row[7]),
        sha256=str(row[8]),
        thumbnail_state=str(row[9]),
        thumbnail_key=str(row[10]),
        preview_state=str(row[11]),
        missing=bool(row[12]),
    )
