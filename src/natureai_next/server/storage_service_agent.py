"""Offline-first linked-storage agent for organisation-controlled file servers.

The agent owns the filesystem mount and local preview cache. It sends only opaque source
identity, relative paths, media metadata and governed work acknowledgements to Fieldora.
Catalogue batches are journalled before transmission so an interrupted or uncertain
network exchange replays the exact same hash-chained batch after restart.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import mimetypes
import sqlite3
import ssl
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from natureai_next.server.linked_storage import (
    LinkedMediaRecord,
    LinkedPreviewWorker,
    LinkedStorageRepository,
    LinkedStorageSource,
    PreviewPriorityQueue,
    _walk_files,
)
from natureai_next.server.storage_exchange import (
    PreviewState,
    StorageCatalogueBatch,
    StorageCatalogueItem,
    StorageObjectState,
    StorageSourceRegistration,
)


@dataclass(frozen=True, slots=True)
class StorageAgentConfig:
    endpoint: str
    service_id: str
    organization_id: str
    storage_id: str
    display_name: str
    root_alias: str
    root_path: Path
    state_root: Path
    certificate: Path
    private_key: Path
    ca_certificate: Path
    project_id: str = ""
    maximum_preview_edge: int = 512

    def validate(self) -> None:
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("storage exchange endpoint must be an HTTPS origin")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("storage exchange endpoint port is invalid") from exc
        if not all(
            value.strip()
            for value in (
                self.service_id,
                self.organization_id,
                self.storage_id,
                self.display_name,
                self.root_alias,
            )
        ):
            raise ValueError("storage agent identity fields are required")
        if "/" in self.root_alias or "\\" in self.root_alias:
            raise ValueError("root alias is an opaque name, not a path")
        self.root_path.resolve(strict=True)
        for path in (self.certificate, self.private_key, self.ca_certificate):
            if not path.is_file():
                raise ValueError(f"storage agent trust file is missing: {path}")
        if not 64 <= int(self.maximum_preview_edge) <= 2048:
            raise ValueError("maximum preview edge must be between 64 and 2048")


class StorageExchange(Protocol):
    def register_source(self, source: StorageSourceRegistration) -> dict[str, Any]: ...
    def submit_catalogue(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def claim_previews(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def complete_preview(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class MutualTLSStorageExchangeClient:
    """mTLS client using one validated HTTPS origin and fixed internal API paths."""

    _ALLOWED_PATHS = frozenset(
        {
            "/internal/v1/storage/sources",
            "/internal/v1/storage/catalogue",
            "/internal/v1/storage/previews/claim",
            "/internal/v1/storage/previews/complete",
        }
    )

    def __init__(
        self,
        endpoint: str,
        certificate: Path,
        private_key: Path,
        ca_certificate: Path,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        parsed = urlsplit(endpoint.strip())
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("storage exchange endpoint must be an HTTPS origin")
        try:
            port = parsed.port or 443
        except ValueError as exc:
            raise ValueError("storage exchange endpoint port is invalid") from exc
        self._hostname = parsed.hostname
        self._port = port
        self._certificate = certificate
        self._private_key = private_key
        self._ca_certificate = ca_certificate
        self._timeout = max(1.0, min(float(timeout_seconds), 120.0))

    def _context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(self._ca_certificate.resolve(strict=True)))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            str(self._certificate.resolve(strict=True)),
            str(self._private_key.resolve(strict=True)),
        )
        return context

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path not in self._ALLOWED_PATHS:
            raise ValueError("storage exchange path is not allowed")
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        connection = http.client.HTTPSConnection(
            self._hostname,
            self._port,
            timeout=self._timeout,
            context=self._context(),
        )
        try:
            connection.request(
                "POST",
                path,
                body=encoded,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise RuntimeError("storage exchange response exceeds limit")
            if not 200 <= response.status < 300:
                try:
                    error_payload = json.loads(raw)
                    detail = (
                        error_payload.get("error", "storage_exchange_rejected")
                        if isinstance(error_payload, dict)
                        else "storage_exchange_rejected"
                    )
                except json.JSONDecodeError:
                    detail = "storage_exchange_rejected"
                raise RuntimeError(f"{detail} ({response.status})")
            result = json.loads(raw)
        finally:
            connection.close()
        if not isinstance(result, dict):
            raise RuntimeError("storage exchange returned an invalid response")
        return result

    def register_source(self, source: StorageSourceRegistration) -> dict[str, Any]:
        return self._post("/internal/v1/storage/sources", asdict(source))

    def submit_catalogue(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/v1/storage/catalogue", payload)

    def claim_previews(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/v1/storage/previews/claim", payload)

    def complete_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/v1/storage/previews/complete", payload)


@dataclass(frozen=True, slots=True)
class AgentScanState:
    storage_id: str
    scan_id: str
    sequence: int
    checkpoint: str
    last_batch_sha256: str
    pending_json: str
    state: str


class StorageAgentJournal:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_agent_scan(
                    storage_id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    checkpoint TEXT NOT NULL,
                    last_batch_sha256 TEXT NOT NULL,
                    pending_json TEXT NOT NULL,
                    state TEXT NOT NULL
                )
                """
            )

    def state(self, storage_id: str) -> AgentScanState | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT storage_id,scan_id,sequence,checkpoint,last_batch_sha256,"
                "pending_json,state FROM storage_agent_scan WHERE storage_id=?",
                (storage_id,),
            ).fetchone()
        return None if row is None else AgentScanState(*row)

    def start(self, storage_id: str) -> AgentScanState:
        current = AgentScanState(storage_id, str(uuid4()), 0, "", "", "", "running")
        self._put(current)
        return current

    def pending(self, state: AgentScanState, payload: dict[str, Any]) -> AgentScanState:
        updated = replace(
            state,
            pending_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            state="running",
        )
        self._put(updated)
        return updated

    def confirm(self, state: AgentScanState, payload: dict[str, Any]) -> AgentScanState:
        updated = replace(
            state,
            sequence=int(payload["sequence"]),
            checkpoint=str(payload.get("checkpoint", "")),
            last_batch_sha256=str(payload["batch_sha256"]),
            pending_json="",
            state="completed" if bool(payload.get("final")) else "running",
        )
        self._put(updated)
        return updated

    def _put(self, state: AgentScanState) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                "INSERT INTO storage_agent_scan VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(storage_id) DO UPDATE SET scan_id=excluded.scan_id,"
                "sequence=excluded.sequence,checkpoint=excluded.checkpoint,"
                "last_batch_sha256=excluded.last_batch_sha256,"
                "pending_json=excluded.pending_json,state=excluded.state",
                (
                    state.storage_id,
                    state.scan_id,
                    state.sequence,
                    state.checkpoint,
                    state.last_batch_sha256,
                    state.pending_json,
                    state.state,
                ),
            )


class LinkedStorageAgent:
    def __init__(self, config: StorageAgentConfig, exchange: StorageExchange | None = None) -> None:
        config.validate()
        self.config = config
        self.config.state_root.mkdir(parents=True, exist_ok=True)
        self.repository = LinkedStorageRepository(config.state_root / "linked-storage.sqlite3")
        self.repository.put_source(
            LinkedStorageSource(
                config.storage_id,
                config.organization_id,
                config.display_name,
                str(config.root_path.resolve(strict=True)),
            )
        )
        self.journal = StorageAgentJournal(config.state_root / "agent-journal.sqlite3")
        self.preview_root = config.state_root / "previews"
        self.preview_queue = PreviewPriorityQueue()
        self.preview_worker = LinkedPreviewWorker(
            self.repository,
            self.preview_root,
            self.preview_queue,
            config.maximum_preview_edge,
        )
        self.exchange = exchange or MutualTLSStorageExchangeClient(
            config.endpoint,
            config.certificate,
            config.private_key,
            config.ca_certificate,
        )

    def register_source(self) -> dict[str, Any]:
        return self.exchange.register_source(
            StorageSourceRegistration(
                self.config.storage_id,
                self.config.organization_id,
                self.config.service_id,
                self.config.display_name,
                self.config.root_alias,
                True,
            )
        )

    def catalogue(self, *, batch_size: int = 250) -> AgentScanState:
        self.register_source()
        batch_size = max(1, min(int(batch_size), 10_000))
        state = self.journal.state(self.config.storage_id)
        if state is None or state.state == "completed":
            state = self.journal.start(self.config.storage_id)
        if state.pending_json:
            pending = json.loads(state.pending_json)
            self.exchange.submit_catalogue(pending)
            state = self.journal.confirm(state, pending)
            if state.state == "completed":
                return state

        items: list[StorageCatalogueItem] = []
        root = self.config.root_path.resolve(strict=True)
        last_relative = state.checkpoint
        for path in _walk_files(root):
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
                stat = resolved.stat()
            except (OSError, ValueError):
                continue
            relative = path.relative_to(root).as_posix()
            if last_relative and relative <= last_relative:
                continue
            local = self.repository.upsert_media(
                LinkedMediaRecord(
                    media_id=str(uuid4()),
                    storage_id=self.config.storage_id,
                    organization_id=self.config.organization_id,
                    project_id=self.config.project_id,
                    relative_path=relative,
                    mime_type=mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    size_bytes=int(stat.st_size),
                    modified_ns=int(stat.st_mtime_ns),
                )
            )
            items.append(self._catalogue_item(local, path.name))
            last_relative = relative
            if len(items) >= batch_size:
                state = self._send_batch(state, tuple(items), last_relative, final=False)
                items.clear()

        state = self._send_batch(state, tuple(items), last_relative, final=True)
        return state

    def process_preview_leases(
        self,
        *,
        worker_id: str,
        limit: int = 20,
        lease_seconds: int = 120,
    ) -> int:
        result = self.exchange.claim_previews(
            {
                "service_id": self.config.service_id,
                "organization_id": self.config.organization_id,
                "storage_id": self.config.storage_id,
                "worker_id": worker_id,
                "limit": max(1, min(int(limit), 200)),
                "lease_seconds": max(30, min(int(lease_seconds), 900)),
            }
        )
        leases = result.get("items", [])
        if not isinstance(leases, list):
            raise RuntimeError("preview claim response is invalid")
        processed = 0
        for lease in leases:
            if not isinstance(lease, dict):
                continue
            object_id = str(lease.get("object_id", ""))
            media_id = str(lease.get("media_id", ""))
            if not object_id or not media_id:
                continue
            local = self.repository.media(object_id)
            state = PreviewState.FAILED
            etag = ""
            if local is not None:
                self.preview_queue.request(object_id, 0, "server-priority-lease")
                rendered = self.preview_worker.run_one()
                if rendered is not None:
                    state = _preview_state(rendered.thumbnail_state)
                    if state is PreviewState.READY and rendered.thumbnail_key:
                        preview = (self.preview_root / rendered.thumbnail_key).resolve(strict=True)
                        preview.relative_to(self.preview_root.resolve())
                        etag = hashlib.sha256(preview.read_bytes()).hexdigest()
            self.exchange.complete_preview(
                {
                    "service_id": self.config.service_id,
                    "organization_id": self.config.organization_id,
                    "storage_id": self.config.storage_id,
                    "worker_id": worker_id,
                    "media_id": media_id,
                    "state": state.value,
                    "thumbnail_etag": etag,
                }
            )
            processed += 1
        return processed

    def run_preview_worker(
        self,
        *,
        worker_id: str,
        poll_seconds: float = 2.0,
        lease_seconds: int = 120,
        stop_after_idle: int = 0,
    ) -> int:
        poll = max(0.1, min(float(poll_seconds), 60.0))
        idle = 0
        processed = 0
        while True:
            count = self.process_preview_leases(
                worker_id=worker_id, lease_seconds=lease_seconds
            )
            processed += count
            if count:
                idle = 0
                continue
            idle += 1
            if stop_after_idle and idle >= stop_after_idle:
                return processed
            time.sleep(poll)

    def _send_batch(
        self,
        state: AgentScanState,
        items: tuple[StorageCatalogueItem, ...],
        checkpoint: str,
        *,
        final: bool,
    ) -> AgentScanState:
        batch = StorageCatalogueBatch(
            batch_id=str(uuid4()),
            storage_id=self.config.storage_id,
            organization_id=self.config.organization_id,
            service_id=self.config.service_id,
            scan_id=state.scan_id,
            sequence=state.sequence + 1,
            final=final,
            checkpoint=checkpoint,
            items=items,
            previous_batch_sha256=state.last_batch_sha256,
        )
        batch = replace(batch, batch_sha256=batch.calculated_sha256())
        payload = _batch_payload(batch)
        state = self.journal.pending(state, payload)
        self.exchange.submit_catalogue(payload)
        return self.journal.confirm(state, payload)

    @staticmethod
    def _catalogue_item(record: LinkedMediaRecord, filename: str) -> StorageCatalogueItem:
        state = _preview_state(record.thumbnail_state)
        return StorageCatalogueItem(
            object_id=record.media_id,
            relative_path=record.relative_path,
            filename=filename,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            modified_ns=record.modified_ns,
            state=StorageObjectState.AVAILABLE,
            sha256=record.sha256,
            thumbnail_state=state,
            thumbnail_etag="",
            project_id=record.project_id,
        )


def _preview_state(value: str) -> PreviewState:
    return {
        "pending": PreviewState.MISSING,
        "working": PreviewState.PROCESSING,
        "ready": PreviewState.READY,
        "unsupported": PreviewState.UNSUPPORTED,
        "failed": PreviewState.FAILED,
    }.get(value, PreviewState.MISSING)


def _batch_payload(batch: StorageCatalogueBatch) -> dict[str, Any]:
    return {
        "batch_id": batch.batch_id,
        "storage_id": batch.storage_id,
        "organization_id": batch.organization_id,
        "service_id": batch.service_id,
        "scan_id": batch.scan_id,
        "sequence": batch.sequence,
        "final": batch.final,
        "checkpoint": batch.checkpoint,
        "previous_batch_sha256": batch.previous_batch_sha256,
        "batch_sha256": batch.batch_sha256,
        "items": [
            {
                "object_id": item.object_id,
                "relative_path": item.relative_path,
                "filename": item.filename,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "modified_ns": item.modified_ns,
                "state": item.state.value,
                "sha256": item.sha256,
                "thumbnail_state": item.thumbnail_state.value,
                "thumbnail_etag": item.thumbnail_etag,
                "project_id": item.project_id,
                "metadata": item.metadata,
            }
            for item in batch.items
        ],
    }
