"""Import planning values and deterministic policy decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PHOTO_EXTENSIONS = frozenset(
    {
        ".avif",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }
)
RAW_EXTENSIONS = frozenset(
    {
        ".3fr",
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
        ".erf",
        ".fff",
        ".iiq",
        ".kdc",
        ".mef",
        ".mos",
        ".mrw",
        ".nef",
        ".nrw",
        ".orf",
        ".pef",
        ".raf",
        ".raw",
        ".rw2",
        ".rwl",
        ".sr2",
        ".srf",
        ".srw",
        ".x3f",
    }
)
SIDECAR_EXTENSIONS = frozenset({".dop", ".pp3", ".thm", ".xmp"})
SOUND_EXTENSIONS = frozenset(
    {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma"}
)
VIDEO_EXTENSIONS = frozenset(
    {".avi", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".webm", ".wmv"}
)
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".csv",
        ".doc",
        ".docm",
        ".docx",
        ".md",
        ".odp",
        ".ods",
        ".odt",
        ".pdf",
        ".pot",
        ".potx",
        ".pps",
        ".ppsx",
        ".ppt",
        ".pptm",
        ".pptx",
        ".rtf",
        ".txt",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
    }
)


class ImportSourceKind(StrEnum):
    PHOTO = "photo"
    RAW_PHOTO = "raw_photo"
    SOUND = "sound"
    VIDEO = "video"
    DOCUMENT = "document"
    SIDECAR = "sidecar"
    UNKNOWN = "unknown"


def classify_import_source(path: Path) -> ImportSourceKind:
    """Classify a source by its final suffix without performing I/O."""
    suffix = path.suffix.casefold()
    if suffix in RAW_EXTENSIONS:
        return ImportSourceKind.RAW_PHOTO
    if suffix in PHOTO_EXTENSIONS:
        return ImportSourceKind.PHOTO
    if suffix in SOUND_EXTENSIONS:
        return ImportSourceKind.SOUND
    if suffix in VIDEO_EXTENSIONS:
        return ImportSourceKind.VIDEO
    if suffix in DOCUMENT_EXTENSIONS:
        return ImportSourceKind.DOCUMENT
    if suffix in SIDECAR_EXTENSIONS:
        return ImportSourceKind.SIDECAR
    return ImportSourceKind.UNKNOWN


class ImportStoragePolicy(StrEnum):
    MANAGED = "managed"
    REFERENCED = "referenced"
    HYBRID = "hybrid"


class DuplicatePolicy(StrEnum):
    SKIP = "skip"
    ADD_FILE_INSTANCE = "add_file_instance"


class SourceDisposition(StrEnum):
    KEEP = "keep"
    DELETE_AFTER_VERIFIED_COPY = "delete_after_verified_copy"


class ImportDecision(StrEnum):
    IMPORT_NEW_ASSET = "import_new_asset"
    ATTACH_TO_EXISTING_ASSET = "attach_to_existing_asset"
    SKIP_EXACT_DUPLICATE = "skip_exact_duplicate"
    REJECT_SOURCE = "reject_source"


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    size: int
    modified_at_us: int


@dataclass(frozen=True, slots=True)
class Fingerprint:
    sha256: str
    size: int
    fast_fingerprint: str


@dataclass(frozen=True, slots=True)
class ImportPlanItem:
    item_key: str
    source: SourceFile
    fingerprint: Fingerprint
    storage_policy: ImportStoragePolicy
    source_disposition: SourceDisposition
    decision: ImportDecision
    existing_asset_id: int | None = None
    planning_error_code: str | None = None
    planning_error_detail: str | None = None


@dataclass(frozen=True, slots=True)
class ImportPlan:
    public_id: str
    created_at_us: int
    duplicate_policy: DuplicatePolicy
    items: tuple[ImportPlanItem, ...]
    source_root: str | None = None
    source_volume_label: str | None = None
    source_volume_serial: str | None = None
    application_version: str | None = None


@dataclass(frozen=True, slots=True)
class ImportItemResult:
    item_key: str
    state: str
    asset_public_id: str | None = None
    file_public_id: str | None = None
    error_code: str | None = None
    source_path: str | None = None


@dataclass(frozen=True, slots=True)
class ImportSummary:
    total: int
    imported: int
    attached: int
    skipped: int
    failed: int
    results: tuple[ImportItemResult, ...]
