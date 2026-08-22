"""Durable export job handlers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from natureai_next.application.exporting import (
    OriginalFileExportService,
    ResumableDerivativeExportService,
    ResumableOriginalFileExportService,
)
from natureai_next.domain.exporting import (
    CollisionPolicy,
    DerivativeExportPlan,
    DerivativeFormat,
    ExportSelection,
    OriginalFileExportPlan,
)
from natureai_next.ports.jobs import JobExecutionContext


class OriginalFileExportJobHandler:
    """Execute a versioned original-file export through the durable job engine."""

    job_type = "export.original_files.v1"
    resource_class = "io"

    def __init__(self, service: OriginalFileExportService) -> None:
        self._service = service

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported original export job payload")
        asset_ids_value = payload.get("asset_public_ids")
        if asset_ids_value is not None and not isinstance(asset_ids_value, list):
            raise ValueError("asset_public_ids must be a list")
        asset_ids = tuple(str(value) for value in (asset_ids_value or ()))
        selection = ExportSelection(asset_ids, include_all_active=not bool(asset_ids))
        plan = OriginalFileExportPlan(
            public_id=context.job.public_id,
            destination_directory=Path(str(payload["destination_directory"])),
            selection=selection,
            naming_template=str(
                payload.get("naming_template", "{original_stem}-{asset_id}{original_ext}")
            ),
            collision_policy=CollisionPolicy(
                str(payload.get("collision_policy", CollisionPolicy.FAIL.value))
            ),
            include_manifest=bool(payload.get("include_manifest", True)),
            verify_source_checksum=bool(payload.get("verify_source_checksum", True)),
            created_at_us=int(payload.get("created_at_us", context.job.created_at_us)),
        )
        context.cancellation.raise_if_cancelled()
        context.report_progress(0, None, "assets", "Exporting original files")
        result = self._service.execute(plan)
        context.report_progress(
            result.asset_count, result.asset_count, "assets", "Original export complete"
        )
        return {
            "asset_count": result.asset_count,
            "bytes_written": result.bytes_written,
            "manifest_path": None if result.manifest_path is None else str(result.manifest_path),
            "manifest_sha256": result.manifest_sha256,
        }


class ResumableOriginalFileExportJobHandler:
    """Execute item-journaled original exports with restart-safe progress."""

    job_type = "export.original_files.v2"
    resource_class = "io"

    def __init__(
        self, service: ResumableOriginalFileExportService, now_us: Callable[[], int]
    ) -> None:
        self._service = service
        self._now_us = now_us

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 2:
            raise ValueError("unsupported resumable original export job payload")
        asset_ids_value = payload.get("asset_public_ids")
        if asset_ids_value is not None and not isinstance(asset_ids_value, list):
            raise ValueError("asset_public_ids must be a list")
        asset_ids = tuple(str(value) for value in (asset_ids_value or ()))
        plan = OriginalFileExportPlan(
            public_id=context.job.public_id,
            destination_directory=Path(str(payload["destination_directory"])),
            selection=ExportSelection(asset_ids, include_all_active=not bool(asset_ids)),
            naming_template=str(
                payload.get("naming_template", "{original_stem}-{asset_id}{original_ext}")
            ),
            collision_policy=CollisionPolicy(
                str(payload.get("collision_policy", CollisionPolicy.FAIL.value))
            ),
            include_manifest=bool(payload.get("include_manifest", True)),
            verify_source_checksum=bool(payload.get("verify_source_checksum", True)),
            created_at_us=int(payload.get("created_at_us", context.job.created_at_us)),
        )
        result = self._service.execute(
            plan,
            now_us=self._now_us,
            cancellation_check=context.cancellation.raise_if_cancelled,
            progress=lambda current, total, message: context.report_progress(
                current, total, "assets", message
            ),
        )
        return {
            "asset_count": result.asset_count,
            "bytes_written": result.bytes_written,
            "manifest_path": None if result.manifest_path is None else str(result.manifest_path),
            "manifest_sha256": result.manifest_sha256,
        }


class ResumableDerivativeExportJobHandler:
    """Execute item-journaled derivative exports with restart-safe progress."""

    job_type = "export.derivatives.v2"
    resource_class = "cpu"

    def __init__(
        self, service: ResumableDerivativeExportService, now_us: Callable[[], int]
    ) -> None:
        self._service = service
        self._now_us = now_us

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 2:
            raise ValueError("unsupported resumable derivative export job payload")
        asset_ids_value = payload.get("asset_public_ids")
        if asset_ids_value is not None and not isinstance(asset_ids_value, list):
            raise ValueError("asset_public_ids must be a list")
        asset_ids = tuple(str(value) for value in (asset_ids_value or ()))
        plan = DerivativeExportPlan(
            public_id=context.job.public_id,
            destination_directory=Path(str(payload["destination_directory"])),
            selection=ExportSelection(asset_ids, include_all_active=not bool(asset_ids)),
            format=DerivativeFormat(str(payload.get("format", DerivativeFormat.JPEG.value))),
            max_width=int(payload.get("max_width", 2048)),
            max_height=int(payload.get("max_height", 2048)),
            quality=int(payload.get("quality", 90)),
            naming_template=str(payload.get("naming_template", "{original_stem}-{asset_id}")),
            collision_policy=CollisionPolicy(
                str(payload.get("collision_policy", CollisionPolicy.FAIL.value))
            ),
            include_xmp_sidecars=bool(payload.get("include_xmp_sidecars", True)),
            include_manifest=bool(payload.get("include_manifest", True)),
            created_at_us=int(payload.get("created_at_us", context.job.created_at_us)),
        )
        result = self._service.execute(
            plan,
            now_us=self._now_us,
            cancellation_check=context.cancellation.raise_if_cancelled,
            progress=lambda current, total, message: context.report_progress(
                current, total, "assets", message
            ),
        )
        return {
            "asset_count": result.asset_count,
            "bytes_written": result.bytes_written,
            "manifest_path": None if result.manifest_path is None else str(result.manifest_path),
            "manifest_sha256": result.manifest_sha256,
        }
