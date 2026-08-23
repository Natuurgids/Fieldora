"""Governed exchange protocol between Fieldora and organisation storage services.

The internal Fieldora server never exposes or directly trusts a client-supplied NAS
path.  A managed storage service owns the filesystem mount, reports catalogue metadata,
and serves bytes/previews only for Fieldora-authorized requests over the service trust
boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StorageObjectState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"


class PreviewState(StrEnum):
    MISSING = "missing"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StorageSourceRegistration:
    storage_id: str
    organization_id: str
    service_id: str
    display_name: str
    root_alias: str
    read_only: bool = True

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.storage_id,
                self.organization_id,
                self.service_id,
                self.display_name,
                self.root_alias,
            )
        ):
            raise ValueError("storage source registration fields are required")
        if "/" in self.root_alias or "\\" in self.root_alias:
            raise ValueError("root_alias is an opaque service-side name, not a path")


@dataclass(frozen=True, slots=True)
class StorageCatalogueItem:
    object_id: str
    relative_path: str
    filename: str
    mime_type: str
    size_bytes: int
    modified_ns: int
    state: StorageObjectState = StorageObjectState.AVAILABLE
    sha256: str = ""
    thumbnail_state: PreviewState = PreviewState.MISSING
    thumbnail_etag: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        relative = _safe_relative_path(self.relative_path)
        if relative != self.relative_path:
            raise ValueError("relative_path must already be normalized")
        if not self.object_id.strip() or not self.filename.strip():
            raise ValueError("catalogue object identity is required")
        if self.size_bytes < 0 or self.modified_ns < 0:
            raise ValueError("invalid catalogue object size/time")
        if self.sha256 and not _valid_sha256(self.sha256):
            raise ValueError("invalid catalogue sha256")


@dataclass(frozen=True, slots=True)
class StorageCatalogueBatch:
    batch_id: str
    storage_id: str
    organization_id: str
    service_id: str
    scan_id: str
    sequence: int
    final: bool
    checkpoint: str
    items: tuple[StorageCatalogueItem, ...]
    previous_batch_sha256: str = ""
    batch_sha256: str = ""

    def canonical_bytes(self) -> bytes:
        payload = {
            "batch_id": self.batch_id,
            "storage_id": self.storage_id,
            "organization_id": self.organization_id,
            "service_id": self.service_id,
            "scan_id": self.scan_id,
            "sequence": self.sequence,
            "final": self.final,
            "checkpoint": self.checkpoint,
            "previous_batch_sha256": self.previous_batch_sha256,
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
                    "metadata": item.metadata,
                }
                for item in self.items
            ],
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    def calculated_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def verify(self) -> bool:
        return bool(self.batch_sha256) and hmac.compare_digest(
            self.batch_sha256, self.calculated_sha256()
        )

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.batch_id,
                self.storage_id,
                self.organization_id,
                self.service_id,
                self.scan_id,
            )
        ):
            raise ValueError("catalogue batch identity is required")
        if self.sequence < 1:
            raise ValueError("catalogue batch sequence starts at 1")
        if len(self.items) > 10_000:
            raise ValueError("catalogue batch exceeds item limit")
        if self.previous_batch_sha256 and not _valid_sha256(self.previous_batch_sha256):
            raise ValueError("invalid previous batch digest")
        if self.batch_sha256 and not _valid_sha256(self.batch_sha256):
            raise ValueError("invalid batch digest")


@dataclass(frozen=True, slots=True)
class GovernedStorageRead:
    request_id: str
    storage_id: str
    object_id: str
    organization_id: str
    subject_id: str
    purpose: str
    start: int
    end: int
    expires_at_epoch: int
    authorization_sha256: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.request_id,
                self.storage_id,
                self.object_id,
                self.organization_id,
                self.subject_id,
                self.purpose,
            )
        ):
            raise ValueError("governed storage read identity is required")
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid governed byte range")
        if not _valid_sha256(self.authorization_sha256):
            raise ValueError("authorization decision digest is required")


@dataclass(frozen=True, slots=True)
class PreviewPriorityRequest:
    request_id: str
    storage_id: str
    organization_id: str
    media_ids: tuple[str, ...]
    priority: int
    reason: str
    requested_by: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.request_id,
                self.storage_id,
                self.organization_id,
                self.reason,
                self.requested_by,
            )
        ):
            raise ValueError("preview priority request fields are required")
        if not self.media_ids or len(self.media_ids) > 1000:
            raise ValueError("preview priority request must contain 1..1000 media ids")
        if len(set(self.media_ids)) != len(self.media_ids):
            raise ValueError("preview priority request contains duplicate media ids")
        if not 0 <= self.priority <= 1000:
            raise ValueError("preview priority must be between 0 and 1000")


def authorization_digest(decision: dict[str, Any]) -> str:
    """Stable digest included in read grants for audit correlation, not authorization."""
    encoded = json.dumps(
        decision, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    parts = tuple(part for part in normalized.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("invalid storage relative path")
    return "/".join(parts)


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
