"""Verified local original-file exports with Windows-safe deterministic naming."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from string import Formatter

from natureai_next.domain.exporting import (
    CollisionPolicy,
    ExportedFileResult,
    ExportFileRecord,
    ExportItemState,
    OriginalFileExportPlan,
    PersistedOriginalExportItem,
)
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes

_ALLOWED_TOKENS = frozenset(
    {"asset_id", "original_stem", "original_ext", "title", "capture_date", "revision"}
)
_INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def validate_naming_template(template: str) -> None:
    if len(template) > 240:
        raise ValueError("naming template is too long")
    fields: list[str] = []
    try:
        for _literal, field_name, format_spec, conversion in Formatter().parse(template):
            if field_name is None:
                continue
            if format_spec or conversion:
                raise ValueError("format specifications and conversions are not supported")
            fields.append(field_name)
    except ValueError as exc:
        raise ValueError(f"invalid naming template: {exc}") from exc
    unknown = sorted(set(fields) - _ALLOWED_TOKENS)
    if unknown:
        raise ValueError(f"unsupported naming template tokens: {', '.join(unknown)}")
    if not fields:
        raise ValueError("naming template must contain at least one token")


def safe_windows_component(value: str, *, fallback: str = "untitled", max_length: int = 180) -> str:
    normalized = _INVALID_WINDOWS_CHARS.sub("_", value)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized:
        normalized = fallback
    stem = normalized.split(".", 1)[0].upper()
    if stem in _RESERVED_WINDOWS_NAMES:
        normalized = f"_{normalized}"
    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip(" .") or fallback
    return normalized


def render_export_filename(template: str, record: ExportFileRecord) -> str:
    validate_naming_template(template)
    original = Path(record.original_name)
    capture_date = "unknown-date"
    if record.capture_time_utc_us is not None:
        capture_date = datetime.fromtimestamp(record.capture_time_utc_us / 1_000_000, UTC).strftime(
            "%Y-%m-%d"
        )
    values = {
        "asset_id": safe_windows_component(record.asset_public_id, fallback="asset"),
        "original_stem": safe_windows_component(original.stem, fallback="original"),
        "original_ext": original.suffix.lower()
        if re.fullmatch(r"\.[a-z0-9]{1,16}", original.suffix.lower())
        else "",
        "title": safe_windows_component(record.title or "untitled"),
        "capture_date": capture_date,
        "revision": str(record.asset_revision),
    }
    rendered = template.format_map(values)
    suffix = original.suffix.lower()
    if not Path(rendered).suffix and suffix:
        rendered += suffix
    return safe_windows_component(
        rendered, fallback=f"{values['asset_id']}{suffix}", max_length=220
    )


def assign_export_paths(
    plan: OriginalFileExportPlan,
    records: tuple[ExportFileRecord, ...],
) -> tuple[tuple[ExportFileRecord, Path], ...]:
    used: set[str] = set()
    assignments: list[tuple[ExportFileRecord, Path]] = []
    for record in records:
        base = Path(render_export_filename(plan.naming_template, record))
        candidate = base
        index = 2
        while candidate.as_posix().casefold() in used or (
            plan.collision_policy is CollisionPolicy.SUFFIX
            and (plan.destination_directory / candidate).exists()
        ):
            if plan.collision_policy is not CollisionPolicy.SUFFIX:
                raise FileExistsError(f"multiple assets resolve to export name {base}")
            candidate = base.with_name(f"{base.stem} ({index}){base.suffix}")
            index += 1
        used.add(candidate.as_posix().casefold())
        assignments.append((record, candidate))
    return tuple(assignments)


class LocalOriginalFileExportWriter:
    """Copy source originals without mutating them and emit a checksummed manifest."""

    @staticmethod
    def assign_items(
        *,
        plan: OriginalFileExportPlan,
        records: tuple[ExportFileRecord, ...],
    ) -> tuple[PersistedOriginalExportItem, ...]:
        return tuple(
            PersistedOriginalExportItem(
                asset_public_id=record.asset_public_id,
                item_order=index,
                source_path=record.source_path,
                source_size_bytes=record.source_size_bytes,
                source_sha256=record.source_sha256,
                relative_output_path=relative_path.as_posix(),
                state=ExportItemState.PENDING,
                attempt_count=0,
            )
            for index, (record, relative_path) in enumerate(assign_export_paths(plan, records))
        )

    def write(
        self,
        *,
        plan: OriginalFileExportPlan,
        records: tuple[ExportFileRecord, ...],
    ) -> tuple[tuple[ExportedFileResult, ...], Path | None, str | None]:
        validate_naming_template(plan.naming_template)
        destination = plan.destination_directory
        destination.mkdir(parents=True, exist_ok=True)
        assignments = assign_export_paths(plan, records)
        self._preflight(plan, assignments)
        staging = Path(tempfile.mkdtemp(prefix=".natureai-export-", dir=destination.parent))
        try:
            staged: list[tuple[Path, Path, ExportedFileResult]] = []
            for record, relative_path in assignments:
                source = record.source_path
                staged_path = staging / relative_path
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                checksum, size = _copy_verified(source, staged_path)
                if size != record.source_size_bytes:
                    raise OSError(f"source size changed during export: {source}")
                if (
                    plan.verify_source_checksum
                    and record.source_sha256
                    and checksum != record.source_sha256.lower()
                ):
                    raise OSError(f"source checksum mismatch: {source}")
                result = ExportedFileResult(
                    record.asset_public_id, relative_path.as_posix(), size, checksum
                )
                staged.append((staged_path, destination / relative_path, result))

            for staged_path, final_path, _result in staged:
                final_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_path, final_path)

            results = tuple(item[2] for item in staged)
            manifest_path: Path | None = None
            manifest_checksum: str | None = None
            if plan.include_manifest:
                manifest_path = destination / "natureai-export-manifest.json"
                manifest = _manifest_bytes(plan, results)
                if manifest_path.exists() and plan.collision_policy is CollisionPolicy.FAIL:
                    raise FileExistsError(manifest_path)
                atomic_write_bytes(manifest_path, manifest)
                manifest_checksum = hashlib.sha256(manifest).hexdigest()
            return results, manifest_path, manifest_checksum
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def write_item(
        self,
        *,
        destination_directory: Path,
        item: PersistedOriginalExportItem,
        collision_policy: CollisionPolicy,
        verify_source_checksum: bool,
    ) -> ExportedFileResult:
        source = item.source_path
        if not source.is_file():
            raise FileNotFoundError(source)
        target = destination_directory / item.relative_output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if self.validate_completed_item(destination_directory=destination_directory, item=item):
                return ExportedFileResult(
                    item.asset_public_id,
                    item.relative_output_path,
                    target.stat().st_size,
                    _sha256_file(target),
                )
            if collision_policy is CollisionPolicy.FAIL:
                raise FileExistsError(target)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.close(fd)
        staged = Path(temp_name)
        try:
            staged.unlink(missing_ok=True)
            checksum, size = _copy_verified(source, staged)
            if size != item.source_size_bytes:
                raise OSError(f"source size changed during export: {source}")
            if (
                verify_source_checksum
                and item.source_sha256
                and checksum != item.source_sha256.lower()
            ):
                raise OSError(f"source checksum mismatch: {source}")
            os.replace(staged, target)
            return ExportedFileResult(
                item.asset_public_id, item.relative_output_path, size, checksum
            )
        finally:
            staged.unlink(missing_ok=True)

    @staticmethod
    def validate_completed_item(
        *,
        destination_directory: Path,
        item: PersistedOriginalExportItem,
    ) -> bool:
        if item.output_size_bytes is None or item.output_sha256 is None:
            return False
        target = destination_directory / item.relative_output_path
        if not target.is_file() or target.stat().st_size != item.output_size_bytes:
            return False
        return _sha256_file(target) == item.output_sha256.lower()

    def write_manifest(
        self,
        *,
        plan: OriginalFileExportPlan,
        files: tuple[ExportedFileResult, ...],
    ) -> tuple[Path | None, str | None]:
        if not plan.include_manifest:
            return None, None
        manifest_path = plan.destination_directory / "natureai-export-manifest.json"
        manifest = _manifest_bytes(plan, files)
        if manifest_path.exists() and plan.collision_policy is CollisionPolicy.FAIL:
            existing = manifest_path.read_bytes()
            if existing != manifest:
                raise FileExistsError(manifest_path)
            return manifest_path, hashlib.sha256(existing).hexdigest()
        atomic_write_bytes(manifest_path, manifest)
        return manifest_path, hashlib.sha256(manifest).hexdigest()

    @staticmethod
    def _preflight(
        plan: OriginalFileExportPlan,
        assignments: tuple[tuple[ExportFileRecord, Path], ...],
    ) -> None:
        for record, relative_path in assignments:
            if not record.source_path.is_file():
                raise FileNotFoundError(record.source_path)
            target = plan.destination_directory / relative_path
            if target.exists() and plan.collision_policy is CollisionPolicy.FAIL:
                raise FileExistsError(target)
        manifest = plan.destination_directory / "natureai-export-manifest.json"
        if (
            plan.include_manifest
            and manifest.exists()
            and plan.collision_policy is CollisionPolicy.FAIL
        ):
            raise FileExistsError(manifest)


def _copy_verified(source: Path, destination: Path) -> tuple[str, int]:
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


def _manifest_bytes(plan: OriginalFileExportPlan, files: tuple[ExportedFileResult, ...]) -> bytes:
    document = {
        "schema_version": 1,
        "application": "NatureAI Next",
        "plan_public_id": plan.public_id,
        "created_at_us": plan.created_at_us,
        "asset_count": len(files),
        "files": [
            {
                "asset_public_id": item.asset_public_id,
                "relative_path": item.relative_path,
                "bytes": item.bytes_written,
                "sha256": item.sha256,
            }
            for item in files
        ],
    }
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
