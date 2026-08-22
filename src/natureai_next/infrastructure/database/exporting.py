"""Read-only SQLite export projections."""

from __future__ import annotations

from pathlib import Path

from natureai_next.domain.exporting import (
    DerivativeExportRecord,
    ExportAssetRecord,
    ExportFileRecord,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteExportCatalogReader:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def read_active_assets(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[ExportAssetRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            parameters: tuple[object, ...] = ()
            restriction = ""
            if public_ids is not None:
                if not public_ids:
                    return ()
                placeholders = ",".join("?" for _ in public_ids)
                restriction = f" AND a.public_id IN ({placeholders})"
                parameters = tuple(public_ids)
            rows = connection.execute(
                """SELECT a.id,a.public_id,a.revision,a.title,a.caption,a.user_notes,a.rating,
                a.color_label,a.pick_state,a.capture_time_utc_us,a.capture_local_text,
                f.normalized_path,f.sha256,f.mime_type,f.format_name,
                ip.pixel_width,ip.pixel_height
                FROM assets a
                LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                LEFT JOIN image_properties ip ON ip.asset_id=a.id
                WHERE a.lifecycle_state='active'"""
                + restriction
                + " ORDER BY a.id",
                parameters,
            ).fetchall()
            records: list[ExportAssetRecord] = []
            for row in rows:
                tags = tuple(
                    value[0]
                    for value in connection.execute(
                        """SELECT t.display_name FROM tags t JOIN asset_tags at ON at.tag_id=t.id
                        WHERE at.asset_id=? ORDER BY t.normalized_name,t.id""",
                        (row["id"],),
                    )
                )
                observations = tuple(
                    {
                        "public_id": value["public_id"],
                        "observation_type": value["observation_type"],
                        "scientific_name": value["scientific_name"],
                        "user_taxon": value["user_taxon"],
                        "life_stage": value["life_stage"],
                        "sex": value["sex"],
                        "count": value["count"],
                        "behavior": value["behavior"],
                        "notes": value["notes"],
                        "confirmation_state": value["confirmation_state"],
                        "revision": value["revision"],
                    }
                    for value in connection.execute(
                        """SELECT o.public_id,o.observation_type,t.scientific_name,
                        ut.display_name AS user_taxon,o.life_stage,o.sex,o.count,o.behavior,
                        o.notes,o.confirmation_state,o.revision
                        FROM observations o LEFT JOIN taxa t ON t.id=o.taxon_id
                        LEFT JOIN user_taxa ut ON ut.id=o.user_taxon_id
                        WHERE o.asset_id=? ORDER BY o.id""",
                        (row["id"],),
                    ).fetchall()
                )
                records.append(
                    ExportAssetRecord(
                        public_id=row["public_id"],
                        revision=row["revision"],
                        title=row["title"],
                        caption=row["caption"],
                        user_notes=row["user_notes"],
                        rating=row["rating"],
                        color_label=row["color_label"],
                        pick_state=row["pick_state"],
                        capture_time_utc_us=row["capture_time_utc_us"],
                        capture_local_text=row["capture_local_text"],
                        primary_path=row["normalized_path"],
                        primary_sha256=row["sha256"],
                        mime_type=row["mime_type"],
                        format_name=row["format_name"],
                        pixel_width=row["pixel_width"],
                        pixel_height=row["pixel_height"],
                        tags=tags,
                        observations=observations,
                    )
                )
            return tuple(records)
        finally:
            connection.close()

    def read_primary_files(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[ExportFileRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            parameters: tuple[object, ...] = ()
            restriction = ""
            if public_ids is not None:
                if not public_ids:
                    return ()
                placeholders = ",".join("?" for _ in public_ids)
                restriction = f" AND a.public_id IN ({placeholders})"
                parameters = tuple(public_ids)
            rows = connection.execute(
                """SELECT a.public_id,a.revision,a.title,a.capture_time_utc_us,
                f.normalized_path,f.sha256,f.file_size
                FROM assets a JOIN file_instances f ON f.id=a.primary_file_instance_id
                WHERE a.lifecycle_state='active' AND f.availability_state='available'"""
                + restriction
                + " ORDER BY a.id",
                parameters,
            ).fetchall()
            return tuple(
                ExportFileRecord(
                    asset_public_id=row["public_id"],
                    asset_revision=row["revision"],
                    title=row["title"],
                    capture_time_utc_us=row["capture_time_utc_us"],
                    source_path=Path(row["normalized_path"]),
                    source_sha256=row["sha256"],
                    source_size_bytes=row["file_size"],
                    original_name=Path(row["normalized_path"]).name,
                )
                for row in rows
            )
        finally:
            connection.close()

    def read_derivative_records(
        self, public_ids: tuple[str, ...] | None
    ) -> tuple[DerivativeExportRecord, ...]:
        assets = self.read_active_assets(public_ids)
        files = self.read_primary_files(public_ids)
        by_id = {item.asset_public_id: item for item in files}
        return tuple(
            DerivativeExportRecord(asset=asset, source=by_id[asset.public_id])
            for asset in assets
            if asset.public_id in by_id
        )
