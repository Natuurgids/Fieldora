"""Portable export-package models for reports, data, previews, and originals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class MissingOriginalPolicy(StrEnum):
    CONTINUE = "continue"
    REQUIRE_ALL = "require_all"
    EXCLUDE_ORIGINALS = "exclude_originals"


class ExportPackageItemState(StrEnum):
    INCLUDED = "included"
    MISSING = "missing"
    EXCLUDED = "excluded"
    CHECKSUM_MISMATCH = "checksum_mismatch"


@dataclass(frozen=True, slots=True)
class ExportPackageOriginal:
    asset_public_id: str
    asset_type: str
    source_path: Path
    relative_path: str
    expected_size_bytes: int | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ExportPackageAttachment:
    source_path: Path
    relative_path: str
    role: str


@dataclass(frozen=True, slots=True)
class ExportPackagePlan:
    public_id: str
    destination_directory: Path
    originals: tuple[ExportPackageOriginal, ...] = ()
    attachments: tuple[ExportPackageAttachment, ...] = ()
    missing_original_policy: MissingOriginalPolicy = MissingOriginalPolicy.CONTINUE
    include_originals: bool = True
    created_at_us: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "missing_original_policy",
            MissingOriginalPolicy(str(self.missing_original_policy)),
        )
        if not self.public_id.strip():
            raise ValueError("export package public ID is required")
        paths = [item.relative_path.casefold() for item in (*self.originals, *self.attachments)]
        if len(paths) != len(set(paths)):
            raise ValueError("export package contains duplicate destination paths")
        for relative in paths:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("export package paths must be relative and contained")


@dataclass(frozen=True, slots=True)
class ExportPackageItemResult:
    relative_path: str
    role: str
    state: ExportPackageItemState
    asset_public_id: str | None = None
    asset_type: str | None = None
    bytes_written: int | None = None
    sha256: str | None = None
    source_path: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ExportPackageResult:
    destination_directory: Path
    manifest_path: Path
    manifest_sha256: str
    items: tuple[ExportPackageItemResult, ...]

    @property
    def included_count(self) -> int:
        return sum(item.state is ExportPackageItemState.INCLUDED for item in self.items)

    @property
    def unavailable_count(self) -> int:
        return sum(
            item.state in {ExportPackageItemState.MISSING, ExportPackageItemState.CHECKSUM_MISMATCH}
            for item in self.items
        )
