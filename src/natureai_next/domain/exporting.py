"""Immutable export planning and result models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ExportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


class CollisionPolicy(StrEnum):
    FAIL = "fail"
    REPLACE = "replace"
    SUFFIX = "suffix"


@dataclass(frozen=True, slots=True)
class ExportSelection:
    asset_public_ids: tuple[str, ...] = ()
    include_all_active: bool = False

    def __post_init__(self) -> None:
        if self.include_all_active == bool(self.asset_public_ids):
            raise ValueError("select either explicit assets or all active assets")
        if len(set(self.asset_public_ids)) != len(self.asset_public_ids):
            raise ValueError("asset selection contains duplicate public IDs")


@dataclass(frozen=True, slots=True)
class ExportPlan:
    public_id: str
    destination: Path
    format: ExportFormat
    selection: ExportSelection
    collision_policy: CollisionPolicy = CollisionPolicy.FAIL
    include_provenance: bool = True
    created_at_us: int = 0

    def __post_init__(self) -> None:
        if not self.public_id.strip():
            raise ValueError("export plan public ID is required")
        if self.destination.name in {"", ".", ".."}:
            raise ValueError("export destination must name a file")


@dataclass(frozen=True, slots=True)
class ExportAssetRecord:
    public_id: str
    revision: int
    title: str | None
    caption: str | None
    user_notes: str | None
    rating: int | None
    color_label: str | None
    pick_state: str | None
    capture_time_utc_us: int | None
    capture_local_text: str | None
    primary_path: str | None
    primary_sha256: str | None
    mime_type: str | None
    format_name: str | None
    pixel_width: int | None
    pixel_height: int | None
    tags: tuple[str, ...]
    observations: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ExportResult:
    plan_public_id: str
    destination: Path
    format: ExportFormat
    asset_count: int
    bytes_written: int
    sha256: str


@dataclass(frozen=True, slots=True)
class OriginalFileExportPlan:
    public_id: str
    destination_directory: Path
    selection: ExportSelection
    naming_template: str = "{original_stem}-{asset_id}{original_ext}"
    collision_policy: CollisionPolicy = CollisionPolicy.FAIL
    include_manifest: bool = True
    verify_source_checksum: bool = True
    created_at_us: int = 0

    def __post_init__(self) -> None:
        if not self.public_id.strip():
            raise ValueError("export plan public ID is required")
        if not self.naming_template.strip():
            raise ValueError("naming template is required")
        if self.destination_directory.name in {"", ".", ".."}:
            raise ValueError("export destination directory is invalid")


@dataclass(frozen=True, slots=True)
class ExportFileRecord:
    asset_public_id: str
    asset_revision: int
    title: str | None
    capture_time_utc_us: int | None
    source_path: Path
    source_sha256: str | None
    source_size_bytes: int
    original_name: str


@dataclass(frozen=True, slots=True)
class ExportedFileResult:
    asset_public_id: str
    relative_path: str
    bytes_written: int
    sha256: str


@dataclass(frozen=True, slots=True)
class OriginalFileExportResult:
    plan_public_id: str
    destination_directory: Path
    files: tuple[ExportedFileResult, ...]
    manifest_path: Path | None
    manifest_sha256: str | None

    @property
    def asset_count(self) -> int:
        return len(self.files)

    @property
    def bytes_written(self) -> int:
        return sum(item.bytes_written for item in self.files)


class ExportPlanState(StrEnum):
    PREPARED = "prepared"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportItemState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PersistedOriginalExportItem:
    asset_public_id: str
    item_order: int
    source_path: Path
    source_size_bytes: int
    source_sha256: str | None
    relative_output_path: str
    state: ExportItemState
    attempt_count: int
    output_size_bytes: int | None = None
    output_sha256: str | None = None
    error_text: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class PersistedOriginalExportPlan:
    public_id: str
    destination_directory: Path
    plan_json: str
    state: ExportPlanState
    created_at_us: int
    modified_at_us: int
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    error_text: str | None = None
    id: int | None = None


class DerivativeFormat(StrEnum):
    JPEG = "jpeg"
    PNG = "png"

    @property
    def file_extension(self) -> str:
        return ".jpg" if self is DerivativeFormat.JPEG else ".png"

    @property
    def pillow_format(self) -> str:
        return "JPEG" if self is DerivativeFormat.JPEG else "PNG"


@dataclass(frozen=True, slots=True)
class DerivativeExportPlan:
    public_id: str
    destination_directory: Path
    selection: ExportSelection
    format: DerivativeFormat = DerivativeFormat.JPEG
    max_width: int = 2048
    max_height: int = 2048
    quality: int = 90
    naming_template: str = "{original_stem}-{asset_id}"
    collision_policy: CollisionPolicy = CollisionPolicy.FAIL
    include_xmp_sidecars: bool = True
    include_manifest: bool = True
    created_at_us: int = 0

    def __post_init__(self) -> None:
        if not self.public_id.strip():
            raise ValueError("export plan public ID is required")
        if self.destination_directory.name in {"", ".", ".."}:
            raise ValueError("export destination directory is invalid")
        if not 1 <= self.max_width <= 32768 or not 1 <= self.max_height <= 32768:
            raise ValueError("derivative dimensions must be between 1 and 32768 pixels")
        if not 1 <= self.quality <= 100:
            raise ValueError("derivative quality must be between 1 and 100")
        if not self.naming_template.strip():
            raise ValueError("naming template is required")


@dataclass(frozen=True, slots=True)
class DerivativeExportRecord:
    asset: ExportAssetRecord
    source: ExportFileRecord


@dataclass(frozen=True, slots=True)
class ExportedDerivativeResult:
    asset_public_id: str
    relative_path: str
    bytes_written: int
    sha256: str
    pixel_width: int
    pixel_height: int
    xmp_relative_path: str | None = None
    xmp_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class DerivativeExportResult:
    plan_public_id: str
    destination_directory: Path
    files: tuple[ExportedDerivativeResult, ...]
    manifest_path: Path | None
    manifest_sha256: str | None

    @property
    def asset_count(self) -> int:
        return len(self.files)

    @property
    def bytes_written(self) -> int:
        return sum(item.bytes_written for item in self.files)


@dataclass(frozen=True, slots=True)
class PersistedDerivativeExportItem:
    asset_public_id: str
    item_order: int
    source_path: Path
    source_size_bytes: int
    source_sha256: str | None
    relative_output_path: str
    xmp_relative_path: str | None
    record_json: str
    state: ExportItemState
    attempt_count: int
    output_size_bytes: int | None = None
    output_sha256: str | None = None
    output_pixel_width: int | None = None
    output_pixel_height: int | None = None
    xmp_size_bytes: int | None = None
    xmp_sha256: str | None = None
    error_text: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class PersistedDerivativeExportPlan:
    public_id: str
    destination_directory: Path
    plan_json: str
    state: ExportPlanState
    created_at_us: int
    modified_at_us: int
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    error_text: str | None = None
    id: int | None = None
