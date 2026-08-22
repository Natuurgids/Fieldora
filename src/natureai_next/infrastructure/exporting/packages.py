"""Verified export-package assembly with explicit missing-original reporting."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from natureai_next.domain.export_packages import (
    ExportPackageAttachment,
    ExportPackageItemResult,
    ExportPackageItemState,
    ExportPackageOriginal,
    ExportPackagePlan,
    ExportPackageResult,
    MissingOriginalPolicy,
)
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes


class LocalExportPackageBuilder:
    """Build one portable directory without failing the whole export by default."""

    def build(self, plan: ExportPackagePlan) -> ExportPackageResult:
        destination = plan.destination_directory
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".aperture-package-", dir=destination.parent))
        results: list[ExportPackageItemResult] = []
        try:
            work: list[tuple[str, object]] = [("attachment", item) for item in plan.attachments]
            work.extend(("original", item) for item in plan.originals)
            worker_count = max(2, min(8, os.cpu_count() or 2, len(work) or 1))

            def copy_one(entry: tuple[str, object]) -> ExportPackageItemResult:
                kind, item = entry
                if kind == "attachment":
                    return self._copy_attachment(staging, item)
                original = item
                if (
                    not plan.include_originals
                    or plan.missing_original_policy is MissingOriginalPolicy.EXCLUDE_ORIGINALS
                ):
                    return ExportPackageItemResult(
                        original.relative_path,
                        "original",
                        ExportPackageItemState.EXCLUDED,
                        original.asset_public_id,
                        original.asset_type,
                        source_path=str(original.source_path),
                        message="Original files were excluded by the export plan.",
                    )
                return self._copy_original(staging, original)

            with ThreadPoolExecutor(
                max_workers=worker_count, thread_name_prefix="aperture-export"
            ) as pool:
                results = list(pool.map(copy_one, work))
            if plan.missing_original_policy is MissingOriginalPolicy.REQUIRE_ALL:
                unavailable = next(
                    (
                        item
                        for item in results
                        if item.role == "original"
                        and item.state is not ExportPackageItemState.INCLUDED
                    ),
                    None,
                )
                if unavailable is not None:
                    raise FileNotFoundError(
                        unavailable.message or unavailable.source_path or unavailable.relative_path
                    )

            manifest = _manifest_bytes(plan, tuple(results))
            manifest_path = staging / "manifest.json"
            atomic_write_bytes(manifest_path, manifest)
            manifest_sha256 = hashlib.sha256(manifest).hexdigest()
            if destination.exists():
                raise FileExistsError(destination)
            os.replace(staging, destination)
            return ExportPackageResult(
                destination, destination / "manifest.json", manifest_sha256, tuple(results)
            )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _copy_attachment(root: Path, item: ExportPackageAttachment) -> ExportPackageItemResult:
        if not item.source_path.is_file():
            raise FileNotFoundError(item.source_path)
        checksum, size = _copy_verified(item.source_path, root / item.relative_path)
        return ExportPackageItemResult(
            item.relative_path,
            item.role,
            ExportPackageItemState.INCLUDED,
            bytes_written=size,
            sha256=checksum,
            source_path=str(item.source_path),
        )

    @staticmethod
    def _copy_original(root: Path, item: ExportPackageOriginal) -> ExportPackageItemResult:
        source = item.source_path
        if not source.is_file():
            return ExportPackageItemResult(
                item.relative_path,
                "original",
                ExportPackageItemState.MISSING,
                item.asset_public_id,
                item.asset_type,
                source_path=str(source),
                message="Original file was unavailable during export.",
            )
        checksum, size = _copy_verified(source, root / item.relative_path)
        if item.expected_size_bytes is not None and size != item.expected_size_bytes:
            (root / item.relative_path).unlink(missing_ok=True)
            return ExportPackageItemResult(
                item.relative_path,
                "original",
                ExportPackageItemState.CHECKSUM_MISMATCH,
                item.asset_public_id,
                item.asset_type,
                source_path=str(source),
                message="Original size no longer matches the library record.",
            )
        if item.expected_sha256 and checksum != item.expected_sha256.lower():
            (root / item.relative_path).unlink(missing_ok=True)
            return ExportPackageItemResult(
                item.relative_path,
                "original",
                ExportPackageItemState.CHECKSUM_MISMATCH,
                item.asset_public_id,
                item.asset_type,
                source_path=str(source),
                message="Original checksum no longer matches the library record.",
            )
        return ExportPackageItemResult(
            item.relative_path,
            "original",
            ExportPackageItemState.INCLUDED,
            item.asset_public_id,
            item.asset_type,
            size,
            checksum,
            str(source),
        )


def _copy_verified(source: Path, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        while chunk := input_stream.read(1024 * 1024):
            output_stream.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    return digest.hexdigest(), size


def _manifest_bytes(plan: ExportPackagePlan, items: tuple[ExportPackageItemResult, ...]) -> bytes:
    document = {
        "schema_version": 1,
        "application": "Aperture",
        "plan_public_id": plan.public_id,
        "created_at_us": plan.created_at_us,
        "missing_original_policy": MissingOriginalPolicy(
            str(plan.missing_original_policy)
        ).value,
        "items": [
            {
                "relative_path": item.relative_path,
                "role": item.role,
                "state": ExportPackageItemState(str(item.state)).value,
                "asset_public_id": item.asset_public_id,
                "asset_type": item.asset_type,
                "bytes": item.bytes_written,
                "sha256": item.sha256,
                "source_path": item.source_path,
                "message": item.message,
            }
            for item in items
        ],
    }
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
