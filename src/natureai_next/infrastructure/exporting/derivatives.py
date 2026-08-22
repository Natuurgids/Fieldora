"""Orientation-correct derivative and XMP sidecar export."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from natureai_next.domain.exporting import (
    CollisionPolicy,
    DerivativeExportPlan,
    DerivativeExportRecord,
    ExportAssetRecord,
    ExportedDerivativeResult,
    ExportFileRecord,
    ExportItemState,
    PersistedDerivativeExportItem,
)
from natureai_next.infrastructure.exporting.files import (
    render_export_filename,
    validate_naming_template,
)
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes
from natureai_next.ports.media import ImageDecoder, RenderRequest


class LocalDerivativeExportWriter:
    """Render bounded derivatives and publish an optional XMP sidecar per asset."""

    def __init__(self, decoder: ImageDecoder) -> None:
        self._decoder = decoder

    def write(
        self,
        *,
        plan: DerivativeExportPlan,
        records: tuple[DerivativeExportRecord, ...],
    ) -> tuple[tuple[ExportedDerivativeResult, ...], Path | None, str | None]:
        validate_naming_template(plan.naming_template)
        destination = plan.destination_directory
        destination.mkdir(parents=True, exist_ok=True)
        assignments = self._assign_paths(plan, records)
        self._preflight(plan, assignments)
        staging = Path(
            tempfile.mkdtemp(prefix=".natureai-derivative-export-", dir=destination.parent)
        )
        try:
            results: list[ExportedDerivativeResult] = []
            staged_outputs: list[tuple[Path, Path]] = []
            for record, relative_path in assignments:
                staged_image = staging / relative_path
                staged_image.parent.mkdir(parents=True, exist_ok=True)
                render = self._decoder.render(
                    RenderRequest(
                        source=record.source.source_path,
                        destination=staged_image,
                        max_width=plan.max_width,
                        max_height=plan.max_height,
                        quality=plan.quality,
                        output_format=plan.format.pillow_format,
                    )
                )
                xmp_relative: str | None = None
                xmp_checksum: str | None = None
                if plan.include_xmp_sidecars:
                    xmp_path = relative_path.with_suffix(relative_path.suffix + ".xmp")
                    xmp_bytes = _xmp_bytes(record)
                    staged_xmp = staging / xmp_path
                    staged_xmp.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_bytes(staged_xmp, xmp_bytes)
                    xmp_relative = xmp_path.as_posix()
                    xmp_checksum = hashlib.sha256(xmp_bytes).hexdigest()
                    staged_outputs.append((staged_xmp, destination / xmp_path))
                results.append(
                    ExportedDerivativeResult(
                        asset_public_id=record.asset.public_id,
                        relative_path=relative_path.as_posix(),
                        bytes_written=render.output_size,
                        sha256=render.output_sha256,
                        pixel_width=render.pixel_width,
                        pixel_height=render.pixel_height,
                        xmp_relative_path=xmp_relative,
                        xmp_sha256=xmp_checksum,
                    )
                )
                staged_outputs.append((staged_image, destination / relative_path))

            for staged, final in staged_outputs:
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, final)

            manifest_path: Path | None = None
            manifest_checksum: str | None = None
            if plan.include_manifest:
                manifest_path = destination / "natureai-derivative-manifest.json"
                payload = _manifest_bytes(plan, tuple(results))
                if manifest_path.exists() and plan.collision_policy is CollisionPolicy.FAIL:
                    raise FileExistsError(manifest_path)
                atomic_write_bytes(manifest_path, payload)
                manifest_checksum = hashlib.sha256(payload).hexdigest()
            return tuple(results), manifest_path, manifest_checksum
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def assign_items(
        self,
        *,
        plan: DerivativeExportPlan,
        records: tuple[DerivativeExportRecord, ...],
    ) -> tuple[PersistedDerivativeExportItem, ...]:
        validate_naming_template(plan.naming_template)
        assignments = self._assign_paths(plan, records)
        return tuple(
            PersistedDerivativeExportItem(
                asset_public_id=record.asset.public_id,
                item_order=index,
                source_path=record.source.source_path,
                source_size_bytes=record.source.source_size_bytes,
                source_sha256=record.source.source_sha256,
                relative_output_path=relative_path.as_posix(),
                xmp_relative_path=(
                    relative_path.with_suffix(relative_path.suffix + ".xmp").as_posix()
                    if plan.include_xmp_sidecars
                    else None
                ),
                record_json=_record_json(record),
                state=ExportItemState.PENDING,
                attempt_count=0,
            )
            for index, (record, relative_path) in enumerate(assignments)
        )

    def write_item(
        self,
        *,
        plan: DerivativeExportPlan,
        item: PersistedDerivativeExportItem,
    ) -> tuple[ExportedDerivativeResult, int | None]:
        source = item.source_path
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.stat().st_size != item.source_size_bytes:
            raise OSError(f"source size changed before derivative export: {source}")
        if item.source_sha256 is not None and _sha256_file(source) != item.source_sha256.lower():
            raise OSError(f"source checksum mismatch: {source}")
        record = _record_from_json(item.record_json)
        target = plan.destination_directory / item.relative_output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and plan.collision_policy is CollisionPolicy.FAIL:
            if not self.validate_completed_item(
                destination_directory=plan.destination_directory, item=item
            ):
                raise FileExistsError(target)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.stem}.", suffix=target.suffix, dir=target.parent
        )
        os.close(fd)
        staged_image = Path(temp_name)
        staged_image.unlink(missing_ok=True)
        staged_xmp: Path | None = None
        try:
            render = self._decoder.render(
                RenderRequest(
                    source=source,
                    destination=staged_image,
                    max_width=plan.max_width,
                    max_height=plan.max_height,
                    quality=plan.quality,
                    output_format=plan.format.pillow_format,
                )
            )
            xmp_checksum: str | None = None
            xmp_size: int | None = None
            if item.xmp_relative_path is not None:
                xmp_target = plan.destination_directory / item.xmp_relative_path
                xmp_target.parent.mkdir(parents=True, exist_ok=True)
                fd, xmp_temp_name = tempfile.mkstemp(
                    prefix=f".{xmp_target.name}.", suffix=".tmp", dir=xmp_target.parent
                )
                os.close(fd)
                staged_xmp = Path(xmp_temp_name)
                xmp_bytes = _xmp_bytes(record)
                with staged_xmp.open("wb") as stream:
                    stream.write(xmp_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                xmp_checksum = hashlib.sha256(xmp_bytes).hexdigest()
                xmp_size = len(xmp_bytes)
                os.replace(staged_xmp, xmp_target)
                staged_xmp = None
            os.replace(staged_image, target)
            return (
                ExportedDerivativeResult(
                    asset_public_id=item.asset_public_id,
                    relative_path=item.relative_output_path,
                    bytes_written=render.output_size,
                    sha256=render.output_sha256,
                    pixel_width=render.pixel_width,
                    pixel_height=render.pixel_height,
                    xmp_relative_path=item.xmp_relative_path,
                    xmp_sha256=xmp_checksum,
                ),
                xmp_size,
            )
        finally:
            staged_image.unlink(missing_ok=True)
            if staged_xmp is not None:
                staged_xmp.unlink(missing_ok=True)

    @staticmethod
    def validate_completed_item(
        *,
        destination_directory: Path,
        item: PersistedDerivativeExportItem,
    ) -> bool:
        if (
            item.output_size_bytes is None
            or item.output_sha256 is None
            or item.output_pixel_width is None
            or item.output_pixel_height is None
        ):
            return False
        target = destination_directory / item.relative_output_path
        if not target.is_file() or target.stat().st_size != item.output_size_bytes:
            return False
        if _sha256_file(target) != item.output_sha256.lower():
            return False
        if item.xmp_relative_path is None:
            return item.xmp_sha256 is None and item.xmp_size_bytes is None
        if item.xmp_sha256 is None or item.xmp_size_bytes is None:
            return False
        xmp_target = destination_directory / item.xmp_relative_path
        return (
            xmp_target.is_file()
            and xmp_target.stat().st_size == item.xmp_size_bytes
            and _sha256_file(xmp_target) == item.xmp_sha256.lower()
        )

    def write_manifest(
        self,
        *,
        plan: DerivativeExportPlan,
        files: tuple[ExportedDerivativeResult, ...],
    ) -> tuple[Path | None, str | None]:
        if not plan.include_manifest:
            return None, None
        manifest_path = plan.destination_directory / "natureai-derivative-manifest.json"
        payload = _manifest_bytes(plan, files)
        if manifest_path.exists() and plan.collision_policy is CollisionPolicy.FAIL:
            existing = manifest_path.read_bytes()
            if existing != payload:
                raise FileExistsError(manifest_path)
            return manifest_path, hashlib.sha256(existing).hexdigest()
        atomic_write_bytes(manifest_path, payload)
        return manifest_path, hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _assign_paths(
        plan: DerivativeExportPlan,
        records: tuple[DerivativeExportRecord, ...],
    ) -> tuple[tuple[DerivativeExportRecord, Path], ...]:
        used: set[str] = set()
        assignments: list[tuple[DerivativeExportRecord, Path]] = []
        for record in records:
            base_name = render_export_filename(plan.naming_template, record.source)
            base = Path(base_name).with_suffix(plan.format.file_extension)
            candidate = base
            suffix_index = 2
            while candidate.as_posix().casefold() in used or (
                plan.collision_policy is CollisionPolicy.SUFFIX
                and (plan.destination_directory / candidate).exists()
            ):
                if plan.collision_policy is not CollisionPolicy.SUFFIX:
                    raise FileExistsError(f"multiple assets resolve to export name {base}")
                candidate = base.with_name(f"{base.stem} ({suffix_index}){base.suffix}")
                suffix_index += 1
            used.add(candidate.as_posix().casefold())
            assignments.append((record, candidate))
        return tuple(assignments)

    @staticmethod
    def _preflight(
        plan: DerivativeExportPlan,
        assignments: tuple[tuple[DerivativeExportRecord, Path], ...],
    ) -> None:
        for record, relative_path in assignments:
            if not record.source.source_path.is_file():
                raise FileNotFoundError(record.source.source_path)
            targets = [plan.destination_directory / relative_path]
            if plan.include_xmp_sidecars:
                targets.append(
                    plan.destination_directory
                    / relative_path.with_suffix(relative_path.suffix + ".xmp")
                )
            if plan.collision_policy is CollisionPolicy.FAIL:
                existing = next((target for target in targets if target.exists()), None)
                if existing is not None:
                    raise FileExistsError(existing)
        manifest = plan.destination_directory / "natureai-derivative-manifest.json"
        if (
            plan.include_manifest
            and manifest.exists()
            and plan.collision_policy is CollisionPolicy.FAIL
        ):
            raise FileExistsError(manifest)


def _xmp_bytes(record: DerivativeExportRecord) -> bytes:
    asset = record.asset
    title = escape(asset.title or "")
    caption = escape(asset.caption or "")
    notes = escape(asset.user_notes or "")
    tags = "".join(f"<rdf:li>{escape(tag)}</rdf:li>" for tag in asset.tags)
    rating = "" if asset.rating is None else str(asset.rating)
    label = escape(asset.color_label or "")
    pick = escape(asset.pick_state or "")
    xml = f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:natureai="https://natureai.local/ns/1.0/" xmp:Rating="{rating}" xmp:Label="{label}" natureai:AssetId="{escape(asset.public_id)}" natureai:Revision="{asset.revision}" natureai:PickState="{pick}">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{caption}</rdf:li></rdf:Alt></dc:description>
   <dc:subject><rdf:Bag>{tags}</rdf:Bag></dc:subject>
   <natureai:UserNotes>{notes}</natureai:UserNotes>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
'''
    return xml.encode("utf-8")


def _manifest_bytes(
    plan: DerivativeExportPlan, files: tuple[ExportedDerivativeResult, ...]
) -> bytes:
    document = {
        "schema_version": 1,
        "application": "NatureAI Next",
        "plan_public_id": plan.public_id,
        "created_at_us": plan.created_at_us,
        "format": plan.format.value,
        "max_width": plan.max_width,
        "max_height": plan.max_height,
        "quality": plan.quality,
        "asset_count": len(files),
        "files": [
            {
                "asset_public_id": item.asset_public_id,
                "relative_path": item.relative_path,
                "bytes": item.bytes_written,
                "sha256": item.sha256,
                "pixel_width": item.pixel_width,
                "pixel_height": item.pixel_height,
                "xmp_relative_path": item.xmp_relative_path,
                "xmp_sha256": item.xmp_sha256,
            }
            for item in files
        ],
    }
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _record_json(record: DerivativeExportRecord) -> str:
    asset = record.asset
    source = record.source
    return json.dumps(
        {
            "asset": {
                "public_id": asset.public_id,
                "revision": asset.revision,
                "title": asset.title,
                "caption": asset.caption,
                "user_notes": asset.user_notes,
                "rating": asset.rating,
                "color_label": asset.color_label,
                "pick_state": asset.pick_state,
                "capture_time_utc_us": asset.capture_time_utc_us,
                "capture_local_text": asset.capture_local_text,
                "primary_path": asset.primary_path,
                "primary_sha256": asset.primary_sha256,
                "mime_type": asset.mime_type,
                "format_name": asset.format_name,
                "pixel_width": asset.pixel_width,
                "pixel_height": asset.pixel_height,
                "tags": list(asset.tags),
                "observations": list(asset.observations),
            },
            "source": {
                "asset_public_id": source.asset_public_id,
                "asset_revision": source.asset_revision,
                "title": source.title,
                "capture_time_utc_us": source.capture_time_utc_us,
                "source_path": str(source.source_path),
                "source_sha256": source.source_sha256,
                "source_size_bytes": source.source_size_bytes,
                "original_name": source.original_name,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_from_json(value: str) -> DerivativeExportRecord:
    document = json.loads(value)
    asset = document["asset"]
    source = document["source"]
    return DerivativeExportRecord(
        asset=ExportAssetRecord(
            public_id=str(asset["public_id"]),
            revision=int(asset["revision"]),
            title=asset["title"],
            caption=asset["caption"],
            user_notes=asset["user_notes"],
            rating=asset["rating"],
            color_label=asset["color_label"],
            pick_state=asset["pick_state"],
            capture_time_utc_us=asset["capture_time_utc_us"],
            capture_local_text=asset["capture_local_text"],
            primary_path=asset["primary_path"],
            primary_sha256=asset["primary_sha256"],
            mime_type=asset["mime_type"],
            format_name=asset["format_name"],
            pixel_width=asset["pixel_width"],
            pixel_height=asset["pixel_height"],
            tags=tuple(str(item) for item in asset["tags"]),
            observations=tuple(dict(item) for item in asset["observations"]),
        ),
        source=ExportFileRecord(
            asset_public_id=str(source["asset_public_id"]),
            asset_revision=int(source["asset_revision"]),
            title=source["title"],
            capture_time_utc_us=source["capture_time_utc_us"],
            source_path=Path(str(source["source_path"])),
            source_sha256=source["source_sha256"],
            source_size_bytes=int(source["source_size_bytes"]),
            original_name=str(source["original_name"]),
        ),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
