"""Production import planning and execution application service."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import subprocess
import wave
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.infrastructure.storage_devices import DeviceRegistry, identify_path
from natureai_next.domain.catalog import (
    Asset,
    AssetLifecycle,
    AvailabilityState,
    FileInstance,
    FileRole,
    MediaType,
    StorageMode,
)
from natureai_next.domain.importing import (
    DuplicatePolicy,
    Fingerprint,
    ImportDecision,
    ImportItemResult,
    ImportPlan,
    ImportPlanItem,
    ImportSourceKind,
    ImportStoragePolicy,
    ImportSummary,
    SourceDisposition,
    SourceFile,
    classify_import_source,
)
from natureai_next.ports.clock import Clock
from natureai_next.ports.identity import UuidGenerator
from natureai_next.ports.importing import (
    CancelCheck,
    FileFingerprinter,
    ImportUnitOfWorkFactory,
    ManagedFileStore,
    SidecarResolver,
    SourceScanner,
)
from natureai_next.ports.media import ImageDecoder, MetadataReader, MetadataResult
from natureai_next.application.derivatives import DerivativeRequest


@dataclass(frozen=True, slots=True)
class _MediaProbe:
    format_name: str
    mime_type: str
    pixel_width: int | None = None
    pixel_height: int | None = None
    orientation: int | None = None
    duration_ms: int | None = None
    sample_rate_hz: int | None = None
    channel_count: int | None = None
    frame_rate: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    page_count: int | None = None


class ImportService:
    def __init__(
        self,
        *,
        uow_factory: ImportUnitOfWorkFactory,
        scanner: SourceScanner,
        fingerprinter: FileFingerprinter,
        managed_store: ManagedFileStore,
        decoder: ImageDecoder,
        metadata_reader: MetadataReader,
        clock: Clock,
        ids: UuidGenerator,
        sidecar_resolver: SidecarResolver | None = None,
        sidecar_store: ManagedFileStore | None = None,
        sidecar_metadata_reader: MetadataReader | None = None,
        derivative_scheduler: object | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.scanner = scanner
        self.fingerprinter = fingerprinter
        self.managed_store = managed_store
        self.decoder = decoder
        self.metadata_reader = metadata_reader
        self.clock = clock
        self.ids = ids
        self.sidecar_resolver = sidecar_resolver
        self.sidecar_store = sidecar_store
        self.sidecar_metadata_reader = sidecar_metadata_reader
        self.derivative_scheduler = derivative_scheduler

    def plan(
        self,
        roots: Iterable[Path],
        *,
        storage_policy: ImportStoragePolicy,
        duplicate_policy: DuplicatePolicy,
        recursive: bool = True,
        source_disposition: SourceDisposition = SourceDisposition.KEEP,
        accepted_source_kinds: frozenset[ImportSourceKind] | None = None,
        cancel: CancelCheck | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> ImportPlan:
        if (
            storage_policy is ImportStoragePolicy.HYBRID
            and source_disposition is SourceDisposition.DELETE_AFTER_VERIFIED_COPY
        ):
            raise ValueError("hybrid imports cannot delete their referenced source")
        root_paths = tuple(Path(root).expanduser().resolve() for root in roots)
        items: list[ImportPlanItem] = []
        planned_hashes: dict[str, ImportPlanItem] = {}
        sources = self.scanner.scan(root_paths, recursive=recursive, cancel=cancel)
        selected_sources = tuple(
            source
            for source in sources
            if accepted_source_kinds is None
            or classify_import_source(source.path) in accepted_source_kinds
        )
        total_sources = len(selected_sources)
        if progress:
            progress(0, total_sources, f"Found {total_sources} supported file(s)")
        for source_index, source in enumerate(selected_sources, 1):
            if cancel:
                cancel()
            if progress:
                progress(
                    source_index - 1,
                    total_sources,
                    f"Checking {source_index} of {total_sources}: {source.path.name}",
                )
            item_key = hashlib.sha256(
                f"{source.path}\0{source.size}\0{source.modified_at_us}".encode()
            ).hexdigest()
            fingerprint = Fingerprint("0" * 64, source.size, "unavailable")
            try:
                unsupported = _obvious_unsupported_format(source.path)
                if unsupported is not None:
                    raise UnsupportedImportFormatError(unsupported)
                unchanged = self._find_unchanged_source(source, storage_policy, cancel)
                if unchanged is not None:
                    fingerprint = Fingerprint(
                        str(unchanged["sha256"]),
                        source.size,
                        str(unchanged["fast_fingerprint"]),
                    )
                    items.append(
                        ImportPlanItem(
                            item_key,
                            source,
                            fingerprint,
                            storage_policy,
                            source_disposition,
                            ImportDecision.SKIP_EXACT_DUPLICATE,
                            int(unchanged["asset_id"]),
                        )
                    )
                    if progress:
                        progress(
                            source_index,
                            total_sources,
                            f"Unchanged duplicate {source_index} of {total_sources}: "
                            f"{source.path.name}",
                        )
                    continue
                fingerprint = self.fingerprinter.fingerprint(source.path, cancel=cancel)
                source_kind = classify_import_source(source.path)
                if source_kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}:
                    try:
                        self.decoder.probe(source.path)
                    except Exception as exc:
                        if source_kind is ImportSourceKind.RAW_PHOTO:
                            raise RawDecoderUnavailableError(
                                f"installed image decoder cannot open recognized RAW file: {source.path.name}"
                            ) from exc
                        raise
            except Exception as exc:
                code = _error_code(exc)
                items.append(
                    ImportPlanItem(
                        item_key,
                        source,
                        fingerprint,
                        storage_policy,
                        source_disposition,
                        ImportDecision.REJECT_SOURCE,
                        None,
                        code,
                        str(exc)[:1000],
                    )
                )
                if progress:
                    progress(
                        source_index,
                        total_sources,
                        f"Could not plan {source_index} of {total_sources}: "
                        f"{source.path.name}",
                    )
                continue
            existing = self._find_existing(fingerprint.sha256)
            decision = ImportDecision.IMPORT_NEW_ASSET
            existing_asset_id = None
            if existing:
                existing_asset_id = existing[0]["asset_id"]
                normalized = _normalized_path(source.path)
                same_path = any(row["path_key"] == normalized[1] for row in existing)
                same_policy = any((row["storage_policy"] or row["storage_mode"]) == storage_policy.value for row in existing)
                # An identical file requested under a different storage policy is a
                # storage conversion/attachment, not a duplicate to discard. Only
                # the same physical path under the same policy is an exact skip.
                decision = (
                    ImportDecision.SKIP_EXACT_DUPLICATE
                    if same_path and same_policy
                    else ImportDecision.ATTACH_TO_EXISTING_ASSET
                )
            elif fingerprint.sha256 in planned_hashes:
                # The first matching item creates the asset during execution;
                # ADD_FILE_INSTANCE resolves that asset by hash at that point.
                decision = (
                    ImportDecision.SKIP_EXACT_DUPLICATE
                    if duplicate_policy is DuplicatePolicy.SKIP
                    else ImportDecision.ATTACH_TO_EXISTING_ASSET
                )
            item = ImportPlanItem(
                item_key,
                source,
                fingerprint,
                storage_policy,
                source_disposition,
                decision,
                existing_asset_id,
            )
            items.append(item)
            if decision is ImportDecision.IMPORT_NEW_ASSET:
                planned_hashes[fingerprint.sha256] = item
            if progress:
                progress(
                    source_index,
                    total_sources,
                    f"Checked {source_index} of {total_sources}: {source.path.name}",
                )
        source_root = _common_source_root(root_paths)
        volume_label, volume_serial = _source_volume_identity(source_root)
        plan = ImportPlan(
            str(self.ids.new_uuid()),
            _now_us(self.clock),
            duplicate_policy,
            tuple(items),
            str(source_root) if source_root else None,
            volume_label,
            volume_serial,
            __version__,
        )
        self._persist_plan(plan)
        return plan

    def load_plan(self, public_id: str) -> ImportPlan:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            header = uow.connection.execute(
                "SELECT id,created_at_us,duplicate_policy,source_root,source_volume_label,source_volume_serial,application_version FROM import_plans WHERE public_id=?",
                (public_id,),
            ).fetchone()
            if header is None:
                raise KeyError(public_id)
            rows = tuple(
                uow.connection.execute(
                    "SELECT * FROM import_plan_items WHERE plan_id=? ORDER BY id", (header["id"],)
                )
            )
        items = tuple(
            ImportPlanItem(
                row["item_key"],
                SourceFile(
                    Path(row["source_path"]), row["source_size"], row["source_modified_at_us"]
                ),
                Fingerprint(row["sha256"], row["source_size"], row["fast_fingerprint"]),
                ImportStoragePolicy(row["storage_policy"]),
                SourceDisposition(row["source_disposition"]),
                ImportDecision(row["decision"]),
                row["existing_asset_id"],
                row["error_code"],
                _result_error_detail(row["result_json"]),
            )
            for row in rows
        )
        return ImportPlan(
            public_id,
            header["created_at_us"],
            DuplicatePolicy(header["duplicate_policy"]),
            items,
            header["source_root"],
            header["source_volume_label"],
            header["source_volume_serial"],
            header["application_version"],
        )

    def execute(
        self,
        plan: ImportPlan,
        *,
        cancel: CancelCheck | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> ImportSummary:
        results: list[ImportItemResult] = []
        self._set_plan_state(plan.public_id, "running")
        total_items = len(plan.items)
        for item_index, item in enumerate(plan.items, 1):
            try:
                if cancel:
                    cancel()
                if progress:
                    progress(
                        item_index - 1,
                        total_items,
                        f"Importing {item_index} of {total_items}: {item.source.path.name}",
                    )
                if item.decision is ImportDecision.REJECT_SOURCE:
                    self._finish_item(
                        plan.public_id, item, "failed", None, None, item.planning_error_code
                    )
                    results.append(
                        ImportItemResult(
                            item.item_key,
                            "failed",
                            error_code=item.planning_error_code,
                            source_path=str(item.source.path),
                        )
                    )
                    if progress:
                        progress(
                            item_index,
                            total_items,
                            f"Rejected {item_index} of {total_items}: {item.source.path.name}",
                        )
                    continue
                if item.decision is ImportDecision.SKIP_EXACT_DUPLICATE:
                    self._finish_item(plan.public_id, item, "skipped", None, None, None)
                    results.append(
                        ImportItemResult(
                            item.item_key, "skipped", source_path=str(item.source.path)
                        )
                    )
                    if progress:
                        progress(
                            item_index,
                            total_items,
                            f"Skipped unchanged {item_index} of {total_items}: "
                            f"{item.source.path.name}",
                        )
                    continue
                result = self._execute_item(plan.public_id, item, cancel)
                results.append(result)
            except Exception as exc:
                code = type(exc).__name__.lower()
                self._finish_item(plan.public_id, item, "failed", None, None, code)
                results.append(
                    ImportItemResult(
                        item.item_key, "failed", error_code=code, source_path=str(item.source.path)
                    )
                )
            if progress:
                progress(
                    item_index,
                    total_items,
                    f"Processed {item_index} of {total_items}: {item.source.path.name}",
                )
        summary = ImportSummary(
            len(results),
            sum(r.state == "imported" for r in results),
            sum(r.state == "attached" for r in results),
            sum(r.state == "skipped" for r in results),
            sum(r.state == "failed" for r in results),
            tuple(results),
        )
        state = "completed_with_errors" if summary.failed else "completed"
        self._complete_plan(plan.public_id, state, summary)
        return summary

    def _execute_item(
        self, plan_id: str, item: ImportPlanItem, cancel: CancelCheck | None
    ) -> ImportItemResult:
        current = self.fingerprinter.fingerprint(item.source.path, cancel=cancel)
        if current.sha256 != item.fingerprint.sha256 or current.size != item.fingerprint.size:
            raise OSError("source changed after import planning")
        source_kind = classify_import_source(item.source.path)
        probe = self._probe(item.source.path, source_kind)
        metadata = (
            self.metadata_reader.read(item.source.path)
            if source_kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}
            else MetadataResult({}, {})
        )
        sidecars = self._prepare_sidecars(item, cancel)
        path = item.source.path
        mode = StorageMode.REFERENCED
        if item.storage_policy in {ImportStoragePolicy.MANAGED, ImportStoragePolicy.HYBRID}:
            path = self.managed_store.place_verified(
                item.source.path, item.fingerprint.sha256, cancel=cancel
            )
            mode = StorageMode.MANAGED
        normalized, path_key = _normalized_path(path)
        now = _now_us(self.clock)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            row = c.execute(
                "SELECT id,state FROM import_plan_items WHERE plan_id=(SELECT id FROM import_plans WHERE public_id=?) AND item_key=?",
                (plan_id, item.item_key),
            ).fetchone()
            if row is None:
                raise RuntimeError("import plan item is not persisted")
            if row["state"] in {"succeeded", "skipped"}:
                saved = c.execute(
                    "SELECT a.public_id asset_public_id,f.public_id file_public_id FROM import_plan_items i LEFT JOIN assets a ON a.id=i.asset_id LEFT JOIN file_instances f ON f.id=i.file_instance_id WHERE i.id=?",
                    (row["id"],),
                ).fetchone()
                return ImportItemResult(
                    item.item_key,
                    "skipped",
                    saved["asset_public_id"],
                    saved["file_public_id"],
                    source_path=str(item.source.path),
                )
            c.execute(
                "UPDATE import_plan_items SET state='running',modified_at_us=? WHERE id=?",
                (now, row["id"]),
            )
            asset_id = item.existing_asset_id
            result_state = "attached"
            if item.decision is ImportDecision.IMPORT_NEW_ASSET:
                asset = uow.assets.add(
                    Asset(
                        str(self.ids.new_uuid()), MediaType.IMAGE, AssetLifecycle.ACTIVE, now, now
                    )
                )
                assert asset.id is not None
                asset_id = asset.id
                result_state = "imported"
            elif asset_id is None:
                existing = c.execute(
                    "SELECT asset_id FROM file_instances WHERE sha256=? ORDER BY id LIMIT 1",
                    (item.fingerprint.sha256,),
                ).fetchone()
                asset_id = existing["asset_id"] if existing is not None else None
            if asset_id is None:
                raise RuntimeError("missing target asset")
            duplicate_path = c.execute(
                "SELECT public_id,id FROM file_instances WHERE path_key=? AND availability_state!='missing'",
                (path_key,),
            ).fetchone()
            if duplicate_path:
                c.execute(
                    "UPDATE import_plan_items SET state='skipped',file_instance_id=?,asset_id=?,modified_at_us=? WHERE id=?",
                    (duplicate_path["id"], asset_id, now, row["id"]),
                )
                uow.commit()
                return ImportItemResult(
                    item.item_key,
                    "skipped",
                    None,
                    duplicate_path["public_id"],
                    source_path=str(item.source.path),
                )
            file = uow.files.add(
                FileInstance(
                    str(self.ids.new_uuid()),
                    asset_id,
                    mode,
                    FileRole.ORIGINAL,
                    normalized,
                    path_key,
                    item.fingerprint.size,
                    item.source.modified_at_us,
                    item.fingerprint.sha256,
                    AvailabilityState.AVAILABLE,
                    probe.mime_type,
                    probe.format_name,
                    now,
                    now,
                )
            )
            assert file.id is not None
            c.execute(
                "UPDATE file_instances SET fast_fingerprint=?,import_source_path=?,verified_at_us=? WHERE id=?",
                (item.fingerprint.fast_fingerprint, str(item.source.path), now, file.id),
            )
            source_file_id: int | None = file.id if item.storage_policy is ImportStoragePolicy.REFERENCED else None
            if item.storage_policy is ImportStoragePolicy.HYBRID:
                source_normalized, source_key = _normalized_path(item.source.path)
                # A Linked -> Hybrid conversion already has an active file instance
                # for this physical source. Reuse it instead of violating the global
                # active-path uniqueness constraint. A new source path still creates
                # a follow-up instance for the existing observation.
                existing_source = c.execute(
                    "SELECT id,asset_id FROM file_instances "
                    "WHERE path_key=? AND availability_state!='missing' LIMIT 1",
                    (source_key,),
                ).fetchone()
                if existing_source is not None:
                    if int(existing_source["asset_id"]) != int(asset_id):
                        raise RuntimeError("source path belongs to a different observation")
                    source_file_id = int(existing_source["id"])
                    c.execute(
                        "UPDATE file_instances SET availability_state='available',"
                        "fast_fingerprint=?,import_source_path=?,verified_at_us=?,modified_at_us=? "
                        "WHERE id=?",
                        (
                            item.fingerprint.fast_fingerprint,
                            str(item.source.path),
                            now,
                            now,
                            source_file_id,
                        ),
                    )
                else:
                    alternate = uow.files.add(
                        FileInstance(
                            str(self.ids.new_uuid()),
                            asset_id,
                            StorageMode.REFERENCED,
                            FileRole.ALTERNATE,
                            source_normalized,
                            source_key,
                            item.fingerprint.size,
                            item.source.modified_at_us,
                            item.fingerprint.sha256,
                            AvailabilityState.AVAILABLE,
                            probe.mime_type,
                            probe.format_name,
                            now,
                            now,
                        )
                    )
                    assert alternate.id is not None
                    c.execute(
                        "UPDATE file_instances SET fast_fingerprint=?,import_source_path=?,verified_at_us=? WHERE id=?",
                        (item.fingerprint.fast_fingerprint, str(item.source.path), now, alternate.id),
                    )
                    source_file_id = alternate.id
            self._record_asset_storage(
                c,
                asset_id=asset_id,
                policy=item.storage_policy,
                source_path=item.source.path,
                source_file_instance_id=source_file_id,
                managed_path=path if mode is StorageMode.MANAGED else None,
                managed_file_instance_id=file.id if mode is StorageMode.MANAGED else None,
                fingerprint=item.fingerprint,
                source_modified_at_us=item.source.modified_at_us,
                now=now,
            )
            imported_keywords: dict[str, str] = {}
            xmp_title: str | None = None
            xmp_caption: str | None = None
            for (
                source_sidecar,
                stored_sidecar,
                sidecar_fingerprint,
                sidecar_mode,
                sidecar_metadata,
            ) in sidecars:
                sidecar_normalized, sidecar_key = _normalized_path(stored_sidecar)
                if c.execute(
                    "SELECT 1 FROM file_instances WHERE path_key=? AND availability_state!='missing'",
                    (sidecar_key,),
                ).fetchone():
                    continue
                sidecar_file = uow.files.add(
                    FileInstance(
                        str(self.ids.new_uuid()),
                        asset_id,
                        sidecar_mode,
                        FileRole.SIDECAR,
                        sidecar_normalized,
                        sidecar_key,
                        sidecar_fingerprint.size,
                        source_sidecar.stat().st_mtime_ns // 1000,
                        sidecar_fingerprint.sha256,
                        AvailabilityState.AVAILABLE,
                        "application/rdf+xml",
                        "XMP",
                        now,
                        now,
                    )
                )
                assert sidecar_file.id is not None
                c.execute(
                    "UPDATE file_instances SET fast_fingerprint=?,import_source_path=?,verified_at_us=? WHERE id=?",
                    (
                        sidecar_fingerprint.fast_fingerprint,
                        str(source_sidecar),
                        now,
                        sidecar_file.id,
                    ),
                )
                if sidecar_metadata is not None:
                    sidecar_payload = json.dumps(
                        sidecar_metadata.raw, sort_keys=True, default=str, separators=(",", ":")
                    ).encode()
                    sidecar_checksum = hashlib.sha256(sidecar_payload).hexdigest()
                    c.execute(
                        "INSERT INTO metadata_snapshots(public_id,file_instance_id,encoding,payload,payload_checksum,created_at_us) VALUES(?,?,?,?,?,?)",
                        (
                            str(self.ids.new_uuid()),
                            sidecar_file.id,
                            "json-utf8",
                            sidecar_payload,
                            sidecar_checksum,
                            now,
                        ),
                    )
                    xmp_title = xmp_title or _text(sidecar_metadata.normalized.get("title"))
                    xmp_caption = xmp_caption or _text(sidecar_metadata.normalized.get("caption"))
                    for keyword in sidecar_metadata.normalized.get("keywords", ()):
                        clean = str(keyword).strip()
                        if clean:
                            imported_keywords.setdefault(clean.casefold(), clean)
            payload = json.dumps(
                metadata.raw, sort_keys=True, default=str, separators=(",", ":")
            ).encode()
            checksum = hashlib.sha256(payload).hexdigest()
            snap = c.execute(
                "INSERT INTO metadata_snapshots(public_id,file_instance_id,encoding,payload,payload_checksum,created_at_us) VALUES(?,?,?,?,?,?)",
                (str(self.ids.new_uuid()), file.id, "json-utf8", payload, checksum, now),
            ).lastrowid
            asset_public = c.execute(
                "SELECT public_id FROM assets WHERE id=?", (asset_id,)
            ).fetchone()[0]
            self._write_media_catalog(
                c,
                asset_public_id=asset_public,
                file_public_id=file.public_id,
                source=item.source.path,
                source_kind=source_kind,
                fingerprint=item.fingerprint,
                probe=probe,
                metadata=metadata,
                now=now,
            )
            if source_kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}:
                c.execute(
                    "INSERT OR REPLACE INTO image_properties(asset_id,file_instance_id,pixel_width,pixel_height,orientation,has_alpha,camera_make,camera_model,lens,metadata_snapshot_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        asset_id,
                        file.id,
                        probe.pixel_width,
                        probe.pixel_height,
                        probe.orientation,
                        0,
                        _text(metadata.normalized.get("camera_make")),
                        _text(metadata.normalized.get("camera_model")),
                        _text(metadata.normalized.get("lens")),
                        snap,
                    ),
                )
                # The catalog row exists before background derivative work starts.
                # This explicit hand-off prevents the gallery from repeatedly
                # trying to manufacture thumbnails itself.
                c.execute(
                    "UPDATE file_instances SET thumbnail_state='imported',modified_at_us=? WHERE id=?",
                    (now, file.id),
                )
            c.execute(
                "UPDATE assets SET primary_file_instance_id=CASE WHEN ? IN ('managed','hybrid') THEN ? ELSE COALESCE(primary_file_instance_id,?) END,capture_local_text=COALESCE(capture_local_text,?),title=COALESCE(title,?),caption=COALESCE(caption,?),modified_at_us=? WHERE id=?",
                (
                    item.storage_policy.value,
                    file.id,
                    file.id,
                    _text(metadata.normalized.get("capture_time_text")),
                    xmp_title,
                    xmp_caption,
                    now,
                    asset_id,
                ),
            )
            for normalized_keyword, display_keyword in imported_keywords.items():
                c.execute(
                    "INSERT OR IGNORE INTO tags(public_id,normalized_name,display_name,created_at_us) VALUES(?,?,?,?)",
                    (str(self.ids.new_uuid()), normalized_keyword, display_keyword, now),
                )
                tag = c.execute(
                    "SELECT id FROM tags WHERE normalized_name=? COLLATE NOCASE",
                    (normalized_keyword,),
                ).fetchone()
                if tag is not None:
                    c.execute(
                        "INSERT OR IGNORE INTO asset_tags(asset_id,tag_id,source,created_at_us) VALUES(?,?,'import',?)",
                        (asset_id, tag["id"], now),
                    )
            latitude, longitude, altitude, location_source = _metadata_location(metadata.normalized)
            if latitude is not None and longitude is not None:
                location_id = c.execute(
                    "INSERT INTO locations(public_id,latitude,longitude,altitude_m,source,confidence,created_at_us) VALUES(?,?,?,?,?,?,?)",
                    (
                        str(self.ids.new_uuid()),
                        latitude,
                        longitude,
                        altitude,
                        location_source or "embedded_metadata",
                        1.0,
                        now,
                    ),
                ).lastrowid
                c.execute(
                    "INSERT OR IGNORE INTO asset_locations(asset_id,location_id,role,precedence) VALUES(?,?,'capture',100)",
                    (asset_id, location_id),
                )
            metadata_state = "succeeded" if metadata.raw else "not_available"
            c.execute(
                "UPDATE import_plan_items SET state='succeeded',asset_id=?,file_instance_id=?,result_json=?,modified_at_us=?,capture_latitude=?,capture_longitude=?,capture_altitude_m=?,location_source=?,metadata_extraction_state=? WHERE id=?",
                (
                    asset_id,
                    file.id,
                    json.dumps({"state": result_state}),
                    now,
                    latitude,
                    longitude,
                    altitude,
                    location_source,
                    metadata_state,
                    row["id"],
                ),
            )
            uow.commit()
        if (
            item.source_disposition is SourceDisposition.DELETE_AFTER_VERIFIED_COPY
            and mode is StorageMode.MANAGED
        ):
            item.source.path.unlink(missing_ok=True)
            for source_sidecar, _stored, _fingerprint, sidecar_mode, _metadata in sidecars:
                if sidecar_mode is StorageMode.MANAGED:
                    source_sidecar.unlink(missing_ok=True)
        if self.derivative_scheduler is not None and source_kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}:
            self.derivative_scheduler.schedule(DerivativeRequest(
                asset_id=asset_id,
                file_instance_id=file.id,
                source=path,
                source_sha256=item.fingerprint.sha256,
            ))
        return ImportItemResult(
            item.item_key,
            result_state,
            asset_public,
            file.public_id,
            source_path=str(item.source.path),
        )

    def _record_asset_storage(
        self, c, *, asset_id: int, policy: ImportStoragePolicy, source_path: Path,
        source_file_instance_id: int | None, managed_path: Path | None,
        managed_file_instance_id: int | None, fingerprint: Fingerprint,
        source_modified_at_us: int | None, now: int,
    ) -> None:
        """Persist the canonical Build 28 storage abstraction in the import transaction."""
        import uuid

        def provider(kind: str, name: str, root: str | None, volume_identity: str | None = None) -> int:
            if volume_identity:
                row = c.execute(
                    "SELECT id FROM storage_providers WHERE volume_identity=?",
                    (volume_identity,),
                ).fetchone()
            else:
                row = c.execute(
                    "SELECT id FROM storage_providers WHERE kind=? AND display_name=?",
                    (kind, name),
                ).fetchone()
            if row is not None:
                return int(row["id"])
            return int(c.execute(
                "INSERT INTO storage_providers(public_id,kind,display_name,root_uri,volume_identity,configuration_json,created_at_us,modified_at_us) VALUES(?,?,?,?,?, '{}',?,?)",
                (str(uuid.uuid4()), kind, name, root, volume_identity, now, now),
            ).lastrowid)

        source_device = identify_path(source_path)
        database_row = c.execute("PRAGMA database_list").fetchone()
        catalog_path = Path(str(database_row[2])) if database_row and database_row[2] else Path(".") / "catalog.db"
        registered_source = DeviceRegistry(catalog_path.parent / "storage_devices.db").register_path(source_path)
        local_provider = provider(
            "removable_volume", source_device.label or "Storage device",
            str(source_device.mount_path), source_device.identity,
        )
        managed_provider = provider(
            "aperture_library", "Aperture Library",
            str(Path(managed_path).parent) if managed_path is not None else None,
        )
        c.execute(
            "INSERT INTO asset_storage_policies(asset_id,policy,created_at_us,modified_at_us) VALUES(?,?,?,?) "
            "ON CONFLICT(asset_id) DO UPDATE SET policy=excluded.policy,modified_at_us=excluded.modified_at_us",
            (asset_id, policy.value, now, now),
        )

        def location(provider_id: int, file_id: int | None, role: str, value: Path, primary: bool) -> None:
            normalized, path_key = _normalized_path(value)
            device = identify_path(value) if role == "source" else None
            if role == "source":
                has_initial = c.execute(
                    "SELECT 1 FROM asset_storage_locations WHERE asset_id=? AND provenance_role='initial' LIMIT 1",
                    (asset_id,),
                ).fetchone() is not None
                provenance_role = "follow_up" if has_initial else "initial"
            else:
                provenance_role = "managed_copy"
            c.execute(
                "INSERT INTO asset_storage_locations(public_id,asset_id,provider_id,file_instance_id,role,normalized_path,path_key,source_uri,file_size,modified_at_observed_us,sha256,fast_fingerprint,health,is_primary,last_verified_at_us,created_at_us,modified_at_us,device_identity,volume_label,relative_path,last_mount_path,device_public_id,location_public_id,provenance_role,discovered_at_us) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(asset_id,role,path_key) DO UPDATE SET file_instance_id=excluded.file_instance_id,health='available',last_verified_at_us=excluded.last_verified_at_us,modified_at_us=excluded.modified_at_us",
                (str(uuid.uuid4()), asset_id, provider_id, file_id, role, normalized, path_key,
                 value.resolve(strict=False).as_uri(), fingerprint.size, source_modified_at_us,
                 fingerprint.sha256, fingerprint.fast_fingerprint, "available", 1 if primary else 0,
                 now, now, now, device.identity if device else None, device.label if device else None,
                 device.relative_path if device else None, str(device.mount_path) if device else None,
                 registered_source.device_public_id if device else None,
                 registered_source.location_public_id if device else None, provenance_role, now),
            )

        # Source provenance is retained for every policy. In Managed mode it is not
        # the preferred working original; in Referenced/Hybrid it is an active source.
        location(local_provider, source_file_instance_id, "source", source_path, policy is ImportStoragePolicy.REFERENCED)
        if managed_path is not None:
            location(managed_provider, managed_file_instance_id, "aperture_master", managed_path, True)

    def _probe(self, path: Path, source_kind: ImportSourceKind) -> _MediaProbe:
        if source_kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}:
            image = self.decoder.probe(path)
            return _MediaProbe(
                image.format_name,
                image.mime_type,
                image.pixel_width,
                image.pixel_height,
                image.orientation,
            )
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        format_name = path.suffix.lstrip(".").upper() or "UNKNOWN"
        if source_kind is ImportSourceKind.SOUND and path.suffix.casefold() == ".wav":
            try:
                with wave.open(str(path), "rb") as stream:
                    rate = stream.getframerate()
                    frames = stream.getnframes()
                    return _MediaProbe(
                        format_name,
                        mime_type,
                        duration_ms=round(frames * 1000 / rate) if rate else None,
                        sample_rate_hz=rate or None,
                        channel_count=stream.getnchannels() or None,
                        audio_codec="PCM",
                    )
            except (OSError, EOFError, wave.Error):
                pass
        if source_kind in {ImportSourceKind.SOUND, ImportSourceKind.VIDEO}:
            probed = _ffprobe(path, format_name, mime_type)
            if probed is not None:
                return probed
        if source_kind is ImportSourceKind.DOCUMENT and path.suffix.casefold() == ".pdf":
            try:
                from pypdf import PdfReader

                pages = len(PdfReader(str(path), strict=False).pages)
            except Exception:
                # Optional document metadata parsing must not reject a supported file.
                pages = None
            return _MediaProbe(format_name, mime_type, page_count=pages)
        return _MediaProbe(format_name, mime_type)

    def _write_media_catalog(
        self,
        connection,
        *,
        asset_public_id: str,
        file_public_id: str,
        source: Path,
        source_kind: ImportSourceKind,
        fingerprint: Fingerprint,
        probe: _MediaProbe,
        metadata: MetadataResult,
        now: int,
    ) -> None:
        asset_type = {
            ImportSourceKind.PHOTO: "photo",
            ImportSourceKind.RAW_PHOTO: "photo",
            ImportSourceKind.SOUND: "sound",
            ImportSourceKind.VIDEO: "video",
            ImportSourceKind.DOCUMENT: "document",
        }[source_kind]
        connection.execute(
            """
            INSERT OR REPLACE INTO library_assets(
                asset_public_id,asset_type,original_filename,primary_file_public_id,
                mime_type,file_extension,file_size_bytes,content_sha256,title,description,
                availability_state,metadata_state,created_at_us,updated_at_us
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                asset_public_id,
                asset_type,
                source.name,
                file_public_id,
                probe.mime_type,
                source.suffix.casefold(),
                fingerprint.size,
                fingerprint.sha256,
                _text(metadata.normalized.get("title")),
                _text(metadata.normalized.get("caption")),
                "available",
                "ready",
                now,
                now,
            ),
        )
        if asset_type == "photo":
            connection.execute(
                """
                INSERT OR REPLACE INTO photo_assets(
                    asset_public_id,pixel_width,pixel_height,orientation,camera_make,
                    camera_model,lens_model
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    asset_public_id,
                    probe.pixel_width,
                    probe.pixel_height,
                    probe.orientation,
                    _text(metadata.normalized.get("camera_make")),
                    _text(metadata.normalized.get("camera_model")),
                    _text(metadata.normalized.get("lens")),
                ),
            )
        elif asset_type == "sound":
            connection.execute(
                """
                INSERT OR REPLACE INTO sound_assets(
                    asset_public_id,duration_ms,sample_rate_hz,channel_count,codec
                ) VALUES(?,?,?,?,?)
                """,
                (
                    asset_public_id,
                    probe.duration_ms,
                    probe.sample_rate_hz,
                    probe.channel_count,
                    probe.audio_codec,
                ),
            )
        elif asset_type == "video":
            connection.execute(
                """
                INSERT OR REPLACE INTO video_assets(
                    asset_public_id,duration_ms,pixel_width,pixel_height,frame_rate,
                    video_codec,audio_codec
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    asset_public_id,
                    probe.duration_ms,
                    probe.pixel_width,
                    probe.pixel_height,
                    probe.frame_rate,
                    probe.video_codec,
                    probe.audio_codec,
                ),
            )
        else:
            connection.execute(
                """
                INSERT OR REPLACE INTO document_assets(
                    asset_public_id,document_format,page_count
                ) VALUES(?,?,?)
                """,
                (asset_public_id, probe.format_name, probe.page_count),
            )

    def _prepare_sidecars(
        self, item: ImportPlanItem, cancel: CancelCheck | None
    ) -> tuple[tuple[Path, Path, Fingerprint, StorageMode, MetadataResult | None], ...]:
        if classify_import_source(item.source.path) not in {
            ImportSourceKind.PHOTO,
            ImportSourceKind.RAW_PHOTO,
        }:
            return ()
        if self.sidecar_resolver is None:
            return ()
        prepared: list[tuple[Path, Path, Fingerprint, StorageMode, MetadataResult | None]] = []
        for source in self.sidecar_resolver.companions(item.source.path):
            try:
                fingerprint = self.fingerprinter.fingerprint(source, cancel=cancel)
                stored = source
                mode = StorageMode.REFERENCED
                if (
                    item.storage_policy in {ImportStoragePolicy.MANAGED, ImportStoragePolicy.HYBRID}
                    and self.sidecar_store is not None
                ):
                    stored = self.sidecar_store.place_verified(
                        source, fingerprint.sha256, cancel=cancel
                    )
                    mode = StorageMode.MANAGED
                sidecar_metadata = None
                if self.sidecar_metadata_reader is not None:
                    try:
                        sidecar_metadata = self.sidecar_metadata_reader.read(source)
                    except (OSError, ValueError):
                        sidecar_metadata = None
                prepared.append((source, stored, fingerprint, mode, sidecar_metadata))
            except OSError:
                continue
        return tuple(prepared)

    def _find_existing(self, sha256: str):
        with self.uow_factory() as uow:
            assert uow.connection is not None
            rows = tuple(
                uow.connection.execute(
                    "SELECT f.id,f.asset_id,f.path_key,f.storage_mode,p.policy AS storage_policy FROM file_instances f LEFT JOIN asset_storage_policies p ON p.asset_id=f.asset_id WHERE f.sha256=? ORDER BY f.id",
                    (sha256,),
                )
            )
        return rows

    def _find_unchanged_source(
        self,
        source: SourceFile,
        storage_policy: ImportStoragePolicy,
        cancel: CancelCheck | None,
    ):
        """Return a safely unchanged prior import without reading the whole file."""
        normalized, path_key = _normalized_path(source.path)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            candidate = uow.connection.execute(
                """
                SELECT f.asset_id,f.sha256,f.fast_fingerprint
                FROM file_instances f
                LEFT JOIN asset_storage_policies p ON p.asset_id=f.asset_id
                WHERE f.availability_state!='missing'
                  AND f.file_size=?
                  AND f.modified_at_observed_us=?
                  AND COALESCE(p.policy,f.storage_mode)=?
                  AND (
                    f.path_key=?
                    OR f.import_source_path=?
                    OR lower(COALESCE(f.import_source_path,''))=?
                  )
                  AND f.sha256 IS NOT NULL
                  AND f.fast_fingerprint IS NOT NULL
                ORDER BY
                  CASE WHEN f.path_key=? THEN 0 ELSE 1 END,
                  f.id
                LIMIT 1
                """,
                (
                    source.size,
                    source.modified_at_us,
                    storage_policy.value,
                    path_key,
                    normalized,
                    normalized.casefold(),
                    path_key,
                ),
            ).fetchone()
        if candidate is None:
            return None
        fast_method = getattr(self.fingerprinter, "fast_fingerprint", None)
        if not callable(fast_method):
            return None
        observed_fast = fast_method(source.path, cancel=cancel)
        return candidate if observed_fast == str(candidate["fast_fingerprint"]) else None

    def _persist_plan(self, plan: ImportPlan) -> None:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            plan_id = c.execute(
                "INSERT INTO import_plans(public_id,schema_version,duplicate_policy,state,created_at_us,source_root,source_volume_label,source_volume_serial,application_version) VALUES(?,2,?,'planned',?,?,?,?,?)",
                (
                    plan.public_id,
                    plan.duplicate_policy,
                    plan.created_at_us,
                    plan.source_root,
                    plan.source_volume_label,
                    plan.source_volume_serial,
                    plan.application_version,
                ),
            ).lastrowid
            c.executemany(
                "INSERT INTO import_plan_items(plan_id,item_key,source_path,source_size,source_modified_at_us,sha256,fast_fingerprint,storage_policy,source_disposition,decision,existing_asset_id,error_code,result_json,modified_at_us,original_filename,original_relative_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        plan_id,
                        i.item_key,
                        str(i.source.path),
                        i.source.size,
                        i.source.modified_at_us,
                        i.fingerprint.sha256,
                        i.fingerprint.fast_fingerprint,
                        i.storage_policy,
                        i.source_disposition,
                        i.decision,
                        i.existing_asset_id,
                        i.planning_error_code,
                        _planning_result_json(i),
                        plan.created_at_us,
                        i.source.path.name,
                        _relative_source_path(i.source.path, plan.source_root),
                    )
                    for i in plan.items
                ],
            )
            uow.commit()

    def _set_plan_state(self, public_id: str, state: str) -> None:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE import_plans SET state=? WHERE public_id=? AND state IN ('planned','running')",
                (state, public_id),
            )
            uow.commit()

    def _finish_item(
        self,
        plan_id: str,
        item: ImportPlanItem,
        state: str,
        asset_id: int | None,
        file_id: int | None,
        error: str | None,
    ) -> None:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE import_plan_items SET state=?,asset_id=?,file_instance_id=?,error_code=?,modified_at_us=? WHERE plan_id=(SELECT id FROM import_plans WHERE public_id=?) AND item_key=?",
                (state, asset_id, file_id, error, _now_us(self.clock), plan_id, item.item_key),
            )
            uow.commit()

    def _complete_plan(self, public_id: str, state: str, summary: ImportSummary) -> None:
        data = {
            "total": summary.total,
            "imported": summary.imported,
            "attached": summary.attached,
            "skipped": summary.skipped,
            "failed": summary.failed,
        }
        with self.uow_factory() as uow:
            assert uow.connection is not None
            uow.connection.execute(
                "UPDATE import_plans SET state=?,completed_at_us=?,summary_json=? WHERE public_id=?",
                (state, _now_us(self.clock), json.dumps(data, sort_keys=True), public_id),
            )
            uow.commit()


def _now_us(clock: Clock) -> int:
    return int(clock.now_utc().timestamp() * 1_000_000)


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _normalized_path(path: Path) -> tuple[str, str]:
    normalized = str(path.expanduser().resolve())
    return normalized, os.path.normcase(normalized).casefold()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, UnsupportedImportFormatError):
        return "unsupported_format"
    if isinstance(exc, RawDecoderUnavailableError):
        return "raw_decoder_unavailable"
    name = type(exc).__name__
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _planning_result_json(item: ImportPlanItem) -> str | None:
    if item.planning_error_detail is None:
        return None
    return json.dumps({"planning_error_detail": item.planning_error_detail}, sort_keys=True)


def _result_error_detail(value: str | None) -> str | None:
    if not value:
        return None
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return None
    detail = data.get("planning_error_detail") if isinstance(data, dict) else None
    return detail if isinstance(detail, str) else None


class UnsupportedImportFormatError(ValueError):
    """An unsupported container was included in an import source."""


class RawDecoderUnavailableError(ValueError):
    """A recognized RAW source is unsupported by the installed decoder."""


def _obvious_unsupported_format(path: Path) -> str | None:
    """Reject archive containers without misclassifying ZIP-based documents.

    Office Open XML and OpenDocument files are ZIP containers by design. Their
    recognized document extensions must pass planning so the document workspace
    can store them and delegate opening to the system application.
    """
    if classify_import_source(path) is ImportSourceKind.DOCUMENT:
        return None
    try:
        with path.open("rb") as stream:
            header = stream.read(8)
    except OSError:
        return None
    if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "ZIP archives are not importable media"
    return None


def _ffprobe(path: Path, format_name: str, mime_type: str) -> _MediaProbe | None:
    """Read common audio/video properties when the optional ffprobe tool exists."""
    try:
        completed = subprocess.run(
            (
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ),
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        document = json.loads(completed.stdout)
    except (
        FileNotFoundError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ):
        return None
    duration = _float_or_none(document.get("format", {}).get("duration"))
    video: dict[str, object] = {}
    audio: dict[str, object] = {}
    for stream in document.get("streams", ()):
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") == "video" and not video:
            video = stream
        elif stream.get("codec_type") == "audio" and not audio:
            audio = stream
    frame_rate = None
    rate = str(video.get("r_frame_rate") or "")
    if "/" in rate:
        numerator, denominator = rate.split("/", 1)
        try:
            frame_rate = float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            pass
    return _MediaProbe(
        format_name,
        mime_type,
        pixel_width=_int_or_none(video.get("width")),
        pixel_height=_int_or_none(video.get("height")),
        duration_ms=round(duration * 1000) if duration is not None else None,
        sample_rate_hz=_int_or_none(audio.get("sample_rate")),
        channel_count=_int_or_none(audio.get("channels")),
        frame_rate=frame_rate,
        video_codec=_text(video.get("codec_name")),
        audio_codec=_text(audio.get("codec_name")),
    )


def _common_source_root(roots: tuple[Path, ...]) -> Path | None:
    if not roots:
        return None
    try:
        return Path(os.path.commonpath([str(path) for path in roots]))
    except ValueError:
        return None


def _source_volume_identity(root: Path | None) -> tuple[str | None, str | None]:
    if root is None:
        return None, None
    anchor = root.anchor or None
    try:
        serial = str(root.stat().st_dev)
    except OSError:
        serial = None
    return anchor, serial


def _relative_source_path(path: Path, source_root: str | None) -> str | None:
    if not source_root:
        return None
    try:
        return str(path.relative_to(Path(source_root)))
    except ValueError:
        return None


def _metadata_location(
    normalized: object,
) -> tuple[float | None, float | None, float | None, str | None]:
    if not hasattr(normalized, "get"):
        return None, None, None, None
    latitude = _float_or_none(normalized.get("capture_latitude"))
    longitude = _float_or_none(normalized.get("capture_longitude"))
    altitude = _float_or_none(normalized.get("capture_altitude_m"))
    return (
        latitude,
        longitude,
        altitude,
        "embedded_metadata" if latitude is not None and longitude is not None else None,
    )


def _float_or_none(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None
