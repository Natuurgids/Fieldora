"""Core catalog entities used by persistence and application services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssetLifecycle(StrEnum):
    ACTIVE = "active"
    TRASHED = "trashed"
    PURGED = "purged"


class MediaType(StrEnum):
    IMAGE = "image"  # legacy photo value retained for RC1 compatibility
    PHOTO = "photo"
    SOUND = "sound"
    VIDEO = "video"
    DOCUMENT = "document"


class StorageMode(StrEnum):
    MANAGED = "managed"
    REFERENCED = "referenced"
    DERIVATIVE = "derivative"


class FileRole(StrEnum):
    ORIGINAL = "original"
    ALTERNATE = "alternate"
    SIDECAR = "sidecar"
    PREVIEW = "preview"
    THUMBNAIL = "thumbnail"
    EXPORT = "export"


class AvailabilityState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    OFFLINE = "offline"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class Asset:
    public_id: str
    media_type: MediaType
    lifecycle_state: AssetLifecycle
    created_at_us: int
    modified_at_us: int
    rating: int | None = None
    title: str | None = None
    caption: str | None = None
    user_notes: str | None = None
    revision: int = 1
    id: int | None = None


@dataclass(frozen=True, slots=True)
class FileInstance:
    public_id: str
    asset_id: int
    storage_mode: StorageMode
    role: FileRole
    normalized_path: str
    path_key: str
    file_size: int
    modified_at_observed_us: int | None
    sha256: str | None
    availability_state: AvailabilityState
    mime_type: str | None
    format_name: str | None
    created_at_us: int
    modified_at_us: int
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Tag:
    public_id: str
    normalized_name: str
    display_name: str
    created_at_us: int
    parent_tag_id: int | None = None
    color: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Collection:
    public_id: str
    collection_type: str
    name: str
    description: str | None
    smart_query_json: str | None
    query_schema_version: int | None
    sort_mode: str
    created_at_us: int
    modified_at_us: int
    id: int | None = None
