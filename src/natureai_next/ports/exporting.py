"""Stable read and write boundaries for local exports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.exporting import (
    CollisionPolicy,
    DerivativeExportPlan,
    DerivativeExportRecord,
    ExportAssetRecord,
    ExportedDerivativeResult,
    ExportedFileResult,
    ExportFileRecord,
    ExportFormat,
    OriginalFileExportPlan,
    PersistedDerivativeExportItem,
    PersistedDerivativeExportPlan,
    PersistedOriginalExportItem,
    PersistedOriginalExportPlan,
)


class ExportCatalogReader(Protocol):
    def read_active_assets(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[ExportAssetRecord, ...]: ...


class ExportFileCatalogReader(Protocol):
    def read_primary_files(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[ExportFileRecord, ...]: ...


class MetadataExportWriter(Protocol):
    def write(
        self,
        *,
        destination: Path,
        format: ExportFormat,
        records: tuple[ExportAssetRecord, ...],
        collision_policy: CollisionPolicy,
        include_provenance: bool,
        plan_public_id: str,
        created_at_us: int,
    ) -> tuple[int, str]: ...


class OriginalFileExportWriter(Protocol):
    def write(
        self,
        *,
        plan: OriginalFileExportPlan,
        records: tuple[ExportFileRecord, ...],
    ) -> tuple[tuple[ExportedFileResult, ...], Path | None, str | None]: ...


class ResumableOriginalExportStore(Protocol):
    def prepare(
        self,
        *,
        plan: OriginalFileExportPlan,
        items: tuple[PersistedOriginalExportItem, ...],
        now_us: int,
    ) -> PersistedOriginalExportPlan: ...
    def get_plan(self, public_id: str) -> PersistedOriginalExportPlan | None: ...
    def list_items(self, plan_public_id: str) -> tuple[PersistedOriginalExportItem, ...]: ...
    def claim_next_item(
        self, plan_public_id: str, now_us: int
    ) -> PersistedOriginalExportItem | None: ...
    def mark_item_succeeded(self, item_id: int, *, size: int, sha256: str, now_us: int) -> None: ...
    def mark_item_failed(self, item_id: int, *, error_text: str, now_us: int) -> None: ...
    def recover_running_items(self, plan_public_id: str, now_us: int) -> int: ...
    def retry_failed_items(self, plan_public_id: str, now_us: int) -> int: ...
    def mark_plan_running(self, plan_public_id: str, now_us: int) -> None: ...
    def mark_plan_succeeded(
        self,
        plan_public_id: str,
        *,
        manifest_path: Path | None,
        manifest_sha256: str | None,
        now_us: int,
    ) -> None: ...
    def mark_plan_failed(self, plan_public_id: str, *, error_text: str, now_us: int) -> None: ...


class ResumableOriginalFileWriter(Protocol):
    def assign_items(
        self, *, plan: OriginalFileExportPlan, records: tuple[ExportFileRecord, ...]
    ) -> tuple[PersistedOriginalExportItem, ...]: ...
    def write_item(
        self,
        *,
        destination_directory: Path,
        item: PersistedOriginalExportItem,
        collision_policy: CollisionPolicy,
        verify_source_checksum: bool,
    ) -> ExportedFileResult: ...
    def validate_completed_item(
        self, *, destination_directory: Path, item: PersistedOriginalExportItem
    ) -> bool: ...
    def write_manifest(
        self, *, plan: OriginalFileExportPlan, files: tuple[ExportedFileResult, ...]
    ) -> tuple[Path | None, str | None]: ...


class DerivativeExportCatalogReader(Protocol):
    def read_derivative_records(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[DerivativeExportRecord, ...]: ...


class DerivativeExportWriter(Protocol):
    def write(
        self,
        *,
        plan: DerivativeExportPlan,
        records: tuple[DerivativeExportRecord, ...],
    ) -> tuple[tuple[ExportedDerivativeResult, ...], Path | None, str | None]: ...


class ResumableDerivativeExportStore(Protocol):
    def prepare(
        self,
        *,
        plan: DerivativeExportPlan,
        items: tuple[PersistedDerivativeExportItem, ...],
        now_us: int,
    ) -> PersistedDerivativeExportPlan: ...
    def get_plan(self, public_id: str) -> PersistedDerivativeExportPlan | None: ...
    def list_items(self, plan_public_id: str) -> tuple[PersistedDerivativeExportItem, ...]: ...
    def claim_next_item(
        self, plan_public_id: str, now_us: int
    ) -> PersistedDerivativeExportItem | None: ...
    def mark_item_succeeded(
        self,
        item_id: int,
        *,
        result: ExportedDerivativeResult,
        xmp_size_bytes: int | None,
        now_us: int,
    ) -> None: ...
    def mark_item_failed(self, item_id: int, *, error_text: str, now_us: int) -> None: ...
    def recover_running_items(self, plan_public_id: str, now_us: int) -> int: ...
    def retry_failed_items(self, plan_public_id: str, now_us: int) -> int: ...
    def mark_plan_running(self, plan_public_id: str, now_us: int) -> None: ...
    def mark_plan_succeeded(
        self,
        plan_public_id: str,
        *,
        manifest_path: Path | None,
        manifest_sha256: str | None,
        now_us: int,
    ) -> None: ...
    def mark_plan_failed(self, plan_public_id: str, *, error_text: str, now_us: int) -> None: ...


class ResumableDerivativeExportWriter(Protocol):
    def assign_items(
        self, *, plan: DerivativeExportPlan, records: tuple[DerivativeExportRecord, ...]
    ) -> tuple[PersistedDerivativeExportItem, ...]: ...
    def write_item(
        self, *, plan: DerivativeExportPlan, item: PersistedDerivativeExportItem
    ) -> tuple[ExportedDerivativeResult, int | None]: ...
    def validate_completed_item(
        self, *, destination_directory: Path, item: PersistedDerivativeExportItem
    ) -> bool: ...
    def write_manifest(
        self, *, plan: DerivativeExportPlan, files: tuple[ExportedDerivativeResult, ...]
    ) -> tuple[Path | None, str | None]: ...
