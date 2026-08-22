"""Persistent media-pipeline job handlers."""

from __future__ import annotations

import json
from pathlib import Path
import time

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory

from natureai_next.infrastructure.imaging.cache import DerivativeCache, DerivativeSpec
from natureai_next.ports.jobs import JobExecutionContext
from natureai_next.ports.media import MetadataReader


class GenerateDerivativeHandler:
    job_type = "media.generate_derivative"
    resource_class = "io"

    def __init__(
        self, cache: DerivativeCache, *, factory: SqliteConnectionFactory | None = None, library_root: Path | None = None
    ) -> None:
        self.cache = cache
        self.factory = factory
        self.library_root = library_root

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        context.cancellation.raise_if_cancelled()
        source = self._resolve_source(payload)
        self._set_state(payload, "processing")
        spec = DerivativeSpec(
            payload["kind"],
            int(payload["max_width"]),
            int(payload["max_height"]),
            int(payload.get("quality", 85)),
            str(payload.get("output_format", "JPEG")),
        )
        context.report_progress(0, 1, "file", "Rendering derivative")
        try:
            output, manifest = self.cache.get_or_create(source, spec, payload.get("source_sha256"))
        except FileNotFoundError:
            self._set_state(payload, "blocked_source_offline")
            raise
        except Exception:
            self._set_state(payload, "failed")
            raise
        if self.factory is not None:
            self._record(payload, output, manifest)
        context.report_progress(1, 1, "file", "Derivative ready")
        return {
            "path": str(output),
            "cache_key": manifest.cache_key,
            "width": manifest.pixel_width,
            "height": manifest.pixel_height,
        }

    def _resolve_source(self, payload: dict[str, object]) -> Path:
        if self.factory is not None:
            connection=self.factory.connect(read_only=True)
            try:
                row=connection.execute("SELECT normalized_path FROM file_instances WHERE id=?",(int(payload["file_instance_id"]),)).fetchone()
                if row is not None and Path(row[0]).is_file(): return Path(row[0])
            finally: connection.close()
        return Path(payload["source"])

    def _set_state(self, payload: dict[str, object], state: str) -> None:
        if self.factory is None: return
        # derivative_cache_entries has a deliberately small persistent-state
        # contract. Running/failed are job states and must never be written here.
        persistent_state = {
            "blocked_source_offline": "missing",
            "failed": "stale",
        }.get(state)
        now = time.time_ns() // 1000
        connection=self.factory.connect()
        try:
            if str(payload["kind"]) == "thumbnail":
                thumbnail_state = "processing" if state == "processing" else "imported"
                connection.execute(
                    "UPDATE file_instances SET thumbnail_state=?,modified_at_us=? WHERE id=?",
                    (thumbnail_state, now, int(payload["file_instance_id"])),
                )
            if persistent_state is not None:
                connection.execute(
                    "UPDATE derivative_cache_entries SET state=?,validated_at_us=? "
                    "WHERE source_file_instance_id=? AND derivative_kind=? AND state!='valid'",
                    (persistent_state, now, int(payload["file_instance_id"]), str(payload["kind"])),
                )
            connection.commit()
        finally: connection.close()

    def _record(self, payload: dict[str, object], output: Path, manifest) -> None:
        now = time.time_ns() // 1000
        relative = str(output.relative_to(self.library_root)) if self.library_root is not None else str(output)
        connection = self.factory.connect()
        try:
            connection.execute(
                """INSERT INTO derivative_cache_entries(
                    asset_id,source_file_instance_id,derivative_kind,cache_key,relative_path,
                    source_sha256,source_size,source_modified_at_us,renderer_identity,parameters_json,
                    output_sha256,output_size,pixel_width,pixel_height,created_at_us,validated_at_us,state
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'valid')
                ON CONFLICT(source_file_instance_id,derivative_kind,renderer_identity,parameters_json) DO UPDATE SET
                    cache_key=excluded.cache_key,relative_path=excluded.relative_path,source_sha256=excluded.source_sha256,
                    source_size=excluded.source_size,source_modified_at_us=excluded.source_modified_at_us,
                    output_sha256=excluded.output_sha256,output_size=excluded.output_size,pixel_width=excluded.pixel_width,
                    pixel_height=excluded.pixel_height,validated_at_us=excluded.validated_at_us,state='valid'""",
                (
                    int(payload["asset_id"]), int(payload["file_instance_id"]), str(payload["kind"]),
                    manifest.cache_key, relative, manifest.source_sha256, manifest.source_size,
                    manifest.source_modified_at_ns // 1000, manifest.renderer_identity,
                    json.dumps(manifest.spec.__dict__ if hasattr(manifest.spec, "__dict__") else {
                        "kind": manifest.spec.kind, "max_width": manifest.spec.max_width,
                        "max_height": manifest.spec.max_height, "quality": manifest.spec.quality,
                        "output_format": manifest.spec.output_format}, sort_keys=True, separators=(",", ":")),
                    manifest.output_sha256, manifest.output_size, manifest.pixel_width, manifest.pixel_height, now, now,
                ),
            )
            if str(payload["kind"]) == "thumbnail":
                connection.execute(
                    "UPDATE file_instances SET thumbnail_state='ready',modified_at_us=? WHERE id=?",
                    (now, int(payload["file_instance_id"])),
                )
            connection.commit()
        finally:
            connection.close()


class ExtractMetadataHandler:
    job_type = "media.extract_metadata"
    resource_class = "io"

    def __init__(self, reader: MetadataReader) -> None:
        self.reader = reader

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        context.cancellation.raise_if_cancelled()
        result = self.reader.read(Path(payload["source"]))
        return {
            "normalized": dict(result.normalized),
            "raw": dict(result.raw),
            "warnings": list(result.warnings),
        }
