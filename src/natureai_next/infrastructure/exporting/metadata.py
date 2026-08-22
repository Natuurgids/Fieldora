"""Deterministic atomic JSON and CSV metadata exporters."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path

from natureai_next.domain.exporting import CollisionPolicy, ExportAssetRecord, ExportFormat
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes


class LocalMetadataExportWriter:
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
    ) -> tuple[int, str]:
        if destination.exists() and collision_policy is CollisionPolicy.FAIL:
            raise FileExistsError(destination)
        content = (
            self._json(records, include_provenance, plan_public_id, created_at_us)
            if format is ExportFormat.JSON
            else self._csv(records, include_provenance)
        )
        atomic_write_bytes(destination, content)
        return len(content), hashlib.sha256(content).hexdigest()

    @staticmethod
    def _json(
        records: tuple[ExportAssetRecord, ...],
        include_provenance: bool,
        plan_public_id: str,
        created_at_us: int,
    ) -> bytes:
        document: dict[str, object] = {
            "schema_version": 1,
            "asset_count": len(records),
            "assets": [asdict(record) for record in records],
        }
        if include_provenance:
            document["export"] = {
                "plan_public_id": plan_public_id,
                "created_at_us": created_at_us,
                "application": "NatureAI Next",
            }
        return (
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _csv(records: tuple[ExportAssetRecord, ...], include_provenance: bool) -> bytes:
        stream = io.StringIO(newline="")
        fields = [
            "public_id",
            "revision",
            "title",
            "caption",
            "user_notes",
            "rating",
            "color_label",
            "pick_state",
            "capture_time_utc_us",
            "capture_local_text",
            "primary_path",
            "primary_sha256",
            "mime_type",
            "format_name",
            "pixel_width",
            "pixel_height",
            "tags",
            "observations_json",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = asdict(record)
            row["tags"] = "|".join(record.tags)
            row["observations_json"] = json.dumps(
                record.observations, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            row.pop("observations")
            writer.writerow(row)
        return stream.getvalue().encode("utf-8-sig")
