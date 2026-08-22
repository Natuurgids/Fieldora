"""Application orchestration for read-only exports."""

from __future__ import annotations

from collections.abc import Callable

from natureai_next.domain.exporting import (
    DerivativeExportPlan,
    DerivativeExportResult,
    ExportedDerivativeResult,
    ExportedFileResult,
    ExportItemState,
    ExportPlan,
    ExportResult,
    OriginalFileExportPlan,
    OriginalFileExportResult,
    PersistedDerivativeExportItem,
)
from natureai_next.ports.exporting import (
    DerivativeExportCatalogReader,
    DerivativeExportWriter,
    ExportCatalogReader,
    ExportFileCatalogReader,
    MetadataExportWriter,
    OriginalFileExportWriter,
    ResumableDerivativeExportStore,
    ResumableDerivativeExportWriter,
    ResumableOriginalExportStore,
    ResumableOriginalFileWriter,
)


class ExportService:
    def __init__(self, reader: ExportCatalogReader, writer: MetadataExportWriter) -> None:
        self._reader = reader
        self._writer = writer

    def execute(self, plan: ExportPlan) -> ExportResult:
        selected = None if plan.selection.include_all_active else plan.selection.asset_public_ids
        records = self._reader.read_active_assets(selected)
        _ensure_selection_complete(selected, tuple(record.public_id for record in records))
        bytes_written, checksum = self._writer.write(
            destination=plan.destination,
            format=plan.format,
            records=records,
            collision_policy=plan.collision_policy,
            include_provenance=plan.include_provenance,
            plan_public_id=plan.public_id,
            created_at_us=plan.created_at_us,
        )
        return ExportResult(
            plan.public_id, plan.destination, plan.format, len(records), bytes_written, checksum
        )


class OriginalFileExportService:
    def __init__(self, reader: ExportFileCatalogReader, writer: OriginalFileExportWriter) -> None:
        self._reader = reader
        self._writer = writer

    def execute(self, plan: OriginalFileExportPlan) -> OriginalFileExportResult:
        selected = None if plan.selection.include_all_active else plan.selection.asset_public_ids
        records = self._reader.read_primary_files(selected)
        _ensure_selection_complete(selected, tuple(record.asset_public_id for record in records))
        exported, manifest_path, manifest_checksum = self._writer.write(plan=plan, records=records)
        return OriginalFileExportResult(
            plan_public_id=plan.public_id,
            destination_directory=plan.destination_directory,
            files=exported,
            manifest_path=manifest_path,
            manifest_sha256=manifest_checksum,
        )


def _ensure_selection_complete(
    selected: tuple[str, ...] | None, found_ids: tuple[str, ...]
) -> None:
    if selected is None:
        return
    found = set(found_ids)
    missing = tuple(public_id for public_id in selected if public_id not in found)
    if missing:
        raise KeyError(f"active assets not found: {', '.join(missing)}")


class ResumableOriginalFileExportService:
    """Execute original exports from a persistent item journal.

    Completed files are checksum-validated and skipped on subsequent runs. Failed
    items are retried once per invocation while successful items remain immutable.
    """

    def __init__(
        self,
        reader: ExportFileCatalogReader,
        writer: ResumableOriginalFileWriter,
        store: ResumableOriginalExportStore,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._store = store

    def execute(
        self,
        plan: OriginalFileExportPlan,
        *,
        now_us: Callable[[], int],
        cancellation_check: Callable[[], None] = lambda: None,
        progress: Callable[[int, int, str], None] = lambda _current, _total, _message: None,
    ) -> OriginalFileExportResult:
        persisted = self._store.get_plan(plan.public_id)
        if persisted is None:
            selected = (
                None if plan.selection.include_all_active else plan.selection.asset_public_ids
            )
            records = self._reader.read_primary_files(selected)
            _ensure_selection_complete(
                selected, tuple(record.asset_public_id for record in records)
            )
            items = self._writer.assign_items(plan=plan, records=records)
            persisted = self._store.prepare(plan=plan, items=items, now_us=now_us())
        self._store.recover_running_items(plan.public_id, now_us())
        self._store.retry_failed_items(plan.public_id, now_us())
        self._store.mark_plan_running(plan.public_id, now_us())

        all_items = self._store.list_items(plan.public_id)
        for item in all_items:
            if item.state is ExportItemState.SUCCEEDED and not self._writer.validate_completed_item(
                destination_directory=plan.destination_directory, item=item
            ):
                if item.id is None:
                    raise RuntimeError("persisted export item has no identity")
                self._store.mark_item_failed(
                    item.id, error_text="completed output failed validation", now_us=now_us()
                )
        self._store.retry_failed_items(plan.public_id, now_us())

        total = len(all_items)
        completed = sum(
            1
            for item in self._store.list_items(plan.public_id)
            if item.state is ExportItemState.SUCCEEDED
        )
        progress(completed, total, "Resuming original export")
        while True:
            cancellation_check()
            item = self._store.claim_next_item(plan.public_id, now_us())
            if item is None:
                break
            if item.id is None:
                raise RuntimeError("claimed export item has no identity")
            try:
                result = self._writer.write_item(
                    destination_directory=plan.destination_directory,
                    item=item,
                    collision_policy=plan.collision_policy,
                    verify_source_checksum=plan.verify_source_checksum,
                )
            except Exception as exc:
                self._store.mark_item_failed(
                    item.id, error_text=f"{type(exc).__name__}: {exc}", now_us=now_us()
                )
            else:
                self._store.mark_item_succeeded(
                    item.id, size=result.bytes_written, sha256=result.sha256, now_us=now_us()
                )
                completed += 1
            progress(completed, total, f"Exported {completed} of {total} originals")

        final_items = self._store.list_items(plan.public_id)
        failures = tuple(item for item in final_items if item.state is ExportItemState.FAILED)
        if failures:
            message = f"{len(failures)} original export item(s) failed"
            self._store.mark_plan_failed(plan.public_id, error_text=message, now_us=now_us())
            raise RuntimeError(message)
        results = tuple(
            ExportedFileResult(
                asset_public_id=item.asset_public_id,
                relative_path=item.relative_output_path,
                bytes_written=item.output_size_bytes or 0,
                sha256=item.output_sha256 or "",
            )
            for item in final_items
        )
        manifest_path, manifest_sha256 = self._writer.write_manifest(plan=plan, files=results)
        self._store.mark_plan_succeeded(
            plan.public_id,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            now_us=now_us(),
        )
        return OriginalFileExportResult(
            plan.public_id, plan.destination_directory, results, manifest_path, manifest_sha256
        )


class DerivativeExportService:
    def __init__(
        self, reader: DerivativeExportCatalogReader, writer: DerivativeExportWriter
    ) -> None:
        self._reader = reader
        self._writer = writer

    def execute(self, plan: DerivativeExportPlan) -> DerivativeExportResult:
        selected = None if plan.selection.include_all_active else plan.selection.asset_public_ids
        records = self._reader.read_derivative_records(selected)
        _ensure_selection_complete(selected, tuple(record.asset.public_id for record in records))
        files, manifest_path, manifest_checksum = self._writer.write(plan=plan, records=records)
        return DerivativeExportResult(
            plan_public_id=plan.public_id,
            destination_directory=plan.destination_directory,
            files=files,
            manifest_path=manifest_path,
            manifest_sha256=manifest_checksum,
        )


class ResumableDerivativeExportService:
    """Execute derivative exports through a persistent per-item journal."""

    def __init__(
        self,
        reader: DerivativeExportCatalogReader,
        writer: ResumableDerivativeExportWriter,
        store: ResumableDerivativeExportStore,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._store = store

    def execute(
        self,
        plan: DerivativeExportPlan,
        *,
        now_us: Callable[[], int],
        cancellation_check: Callable[[], None] = lambda: None,
        progress: Callable[[int, int, str], None] = lambda _current, _total, _message: None,
    ) -> DerivativeExportResult:
        persisted = self._store.get_plan(plan.public_id)
        if persisted is None:
            selected = (
                None if plan.selection.include_all_active else plan.selection.asset_public_ids
            )
            records = self._reader.read_derivative_records(selected)
            _ensure_selection_complete(
                selected, tuple(record.asset.public_id for record in records)
            )
            items = self._writer.assign_items(plan=plan, records=records)
            self._store.prepare(plan=plan, items=items, now_us=now_us())
        self._store.recover_running_items(plan.public_id, now_us())
        self._store.retry_failed_items(plan.public_id, now_us())
        self._store.mark_plan_running(plan.public_id, now_us())

        initial_items = self._store.list_items(plan.public_id)
        for item in initial_items:
            if item.state is ExportItemState.SUCCEEDED and not self._writer.validate_completed_item(
                destination_directory=plan.destination_directory, item=item
            ):
                if item.id is None:
                    raise RuntimeError("persisted derivative export item has no identity")
                self._store.mark_item_failed(
                    item.id,
                    error_text="completed derivative output failed validation",
                    now_us=now_us(),
                )
        self._store.retry_failed_items(plan.public_id, now_us())

        current_items = self._store.list_items(plan.public_id)
        total = len(current_items)
        completed = sum(1 for item in current_items if item.state is ExportItemState.SUCCEEDED)
        progress(completed, total, "Resuming derivative export")
        while True:
            cancellation_check()
            item = self._store.claim_next_item(plan.public_id, now_us())
            if item is None:
                break
            if item.id is None:
                raise RuntimeError("claimed derivative export item has no identity")
            try:
                result, xmp_size = self._writer.write_item(plan=plan, item=item)
            except Exception as exc:
                self._store.mark_item_failed(
                    item.id, error_text=f"{type(exc).__name__}: {exc}", now_us=now_us()
                )
            else:
                self._store.mark_item_succeeded(
                    item.id, result=result, xmp_size_bytes=xmp_size, now_us=now_us()
                )
                completed += 1
            progress(completed, total, f"Exported {completed} of {total} derivatives")

        final_items = self._store.list_items(plan.public_id)
        failures = tuple(item for item in final_items if item.state is ExportItemState.FAILED)
        if failures:
            message = f"{len(failures)} derivative export item(s) failed"
            self._store.mark_plan_failed(plan.public_id, error_text=message, now_us=now_us())
            raise RuntimeError(message)
        results = tuple(_derivative_result_from_item(item) for item in final_items)
        manifest_path, manifest_sha256 = self._writer.write_manifest(plan=plan, files=results)
        self._store.mark_plan_succeeded(
            plan.public_id,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            now_us=now_us(),
        )
        return DerivativeExportResult(
            plan_public_id=plan.public_id,
            destination_directory=plan.destination_directory,
            files=results,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
        )


def _derivative_result_from_item(item: PersistedDerivativeExportItem) -> ExportedDerivativeResult:
    if (
        item.output_size_bytes is None
        or item.output_sha256 is None
        or item.output_pixel_width is None
        or item.output_pixel_height is None
    ):
        raise RuntimeError(
            f"derivative export item {item.asset_public_id} has incomplete output metadata"
        )
    return ExportedDerivativeResult(
        asset_public_id=item.asset_public_id,
        relative_path=item.relative_output_path,
        bytes_written=item.output_size_bytes,
        sha256=item.output_sha256,
        pixel_width=item.output_pixel_width,
        pixel_height=item.output_pixel_height,
        xmp_relative_path=item.xmp_relative_path,
        xmp_sha256=item.xmp_sha256,
    )
