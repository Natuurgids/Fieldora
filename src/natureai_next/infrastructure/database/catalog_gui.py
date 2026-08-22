"""SQLite adapters for GUI catalog projections and optimistic edits."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.ports.catalog_queries import (
    AssetDetail,
    AssetGridRow,
    AssetPage,
    BatchReviewResult,
    BatchReviewTarget,
    MetadataChangeResult,
    MetadataPatch,
    ReviewPatch,
)


class SqliteCatalogGuiAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory
        self._library_root = factory.database_path.parent

    def _derivative_path(self, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = self._library_root / path
        return str(path.resolve())

    def page_assets(self, *, limit: int, after_id: int | None = None) -> AssetPage:
        connection = self._factory.connect()
        try:
            rows = connection.execute(
                """SELECT a.id,a.public_id,a.revision,a.title,a.rating,a.color_label,a.pick_state,a.capture_time_utc_us,
                f.public_id file_public_id,f.normalized_path,ip.pixel_width,ip.pixel_height,
                (SELECT d.relative_path FROM derivative_cache_entries d WHERE d.asset_id=a.id AND d.derivative_kind='thumbnail' AND d.state='valid' ORDER BY d.created_at_us DESC LIMIT 1) thumbnail_path
                FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                LEFT JOIN image_properties ip ON ip.asset_id=a.id
                WHERE a.lifecycle_state='active' AND f.thumbnail_state='ready' AND a.id>?
                AND (
                    NOT EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id)
                    OR EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id AND la.asset_type='photo')
                )
                ORDER BY a.id LIMIT ?""",
                (after_id or 0, limit),
            ).fetchall()
            total = int(
                connection.execute(
                    """SELECT COUNT(*) FROM assets a JOIN file_instances f ON f.id=a.primary_file_instance_id WHERE a.lifecycle_state='active' AND f.thumbnail_state='ready'
                    AND (
                        NOT EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id)
                        OR EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id AND la.asset_type='photo')
                    )"""
                ).fetchone()[0]
            )
            projected = tuple(
                AssetGridRow(
                    public_id=r["public_id"],
                    internal_id=r["id"],
                    revision=r["revision"],
                    title=r["title"],
                    rating=r["rating"],
                    color_label=r["color_label"],
                    pick_state=r["pick_state"],
                    capture_time_utc_us=r["capture_time_utc_us"],
                    primary_file_public_id=r["file_public_id"],
                    primary_path=r["normalized_path"],
                    thumbnail_path=self._derivative_path(r["thumbnail_path"]),
                    pixel_width=r["pixel_width"],
                    pixel_height=r["pixel_height"],
                )
                for r in rows
            )
            return AssetPage(
                projected, projected[-1].internal_id if len(projected) == limit else None, total
            )
        finally:
            connection.close()

    def page_assets_by_public_ids(self, public_ids: tuple[str, ...]) -> AssetPage:
        if not public_ids:
            return AssetPage((), None, 0)
        connection = self._factory.connect()
        try:
            placeholders = ",".join("?" for _ in public_ids)
            rows = connection.execute(
                f"""SELECT a.id,a.public_id,a.revision,a.title,a.rating,a.color_label,a.pick_state,a.capture_time_utc_us,
                f.public_id file_public_id,f.normalized_path,ip.pixel_width,ip.pixel_height,
                (SELECT d.relative_path FROM derivative_cache_entries d WHERE d.asset_id=a.id AND d.derivative_kind='thumbnail' AND d.state='valid' ORDER BY d.created_at_us DESC LIMIT 1) thumbnail_path
                FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                LEFT JOIN image_properties ip ON ip.asset_id=a.id
                WHERE a.lifecycle_state='active' AND f.thumbnail_state='ready' AND a.public_id IN ({placeholders})
                AND (
                    NOT EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id)
                    OR EXISTS(SELECT 1 FROM library_assets la WHERE la.asset_public_id=a.public_id AND la.asset_type='photo')
                )
                ORDER BY a.id DESC""",
                public_ids,
            ).fetchall()
            projected = tuple(
                AssetGridRow(
                    public_id=r["public_id"],
                    internal_id=r["id"],
                    revision=r["revision"],
                    title=r["title"],
                    rating=r["rating"],
                    color_label=r["color_label"],
                    pick_state=r["pick_state"],
                    capture_time_utc_us=r["capture_time_utc_us"],
                    primary_file_public_id=r["file_public_id"],
                    primary_path=r["normalized_path"],
                    thumbnail_path=self._derivative_path(r["thumbnail_path"]),
                    pixel_width=r["pixel_width"],
                    pixel_height=r["pixel_height"],
                )
                for r in rows
            )
            return AssetPage(projected, None, len(projected))
        finally:
            connection.close()


    def derivative_path(self, public_id: str, kind: str) -> str | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                """SELECT d.relative_path
                FROM derivative_cache_entries d
                JOIN assets a ON a.id=d.asset_id
                WHERE a.public_id=? AND a.lifecycle_state='active'
                  AND d.derivative_kind=? AND d.state='valid'
                ORDER BY d.validated_at_us DESC,d.created_at_us DESC LIMIT 1""",
                (public_id, kind),
            ).fetchone()
            return None if row is None else self._derivative_path(str(row["relative_path"]))
        finally:
            connection.close()

    def get_asset_detail(self, public_id: str) -> AssetDetail | None:
        c = self._factory.connect()
        try:
            r = c.execute(
                """SELECT a.*,f.normalized_path,f.mime_type,f.format_name,f.storage_mode,f.availability_state,f.import_source_path,ip.pixel_width,ip.pixel_height FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id LEFT JOIN image_properties ip ON ip.asset_id=a.id WHERE a.public_id=?""",
                (public_id,),
            ).fetchone()
            if r is None:
                return None
            tags = tuple(
                x[0]
                for x in c.execute(
                    "SELECT t.display_name FROM tags t JOIN asset_tags at ON at.tag_id=t.id WHERE at.asset_id=? AND at.source='user' ORDER BY t.normalized_name",
                    (r["id"],),
                )
            )

            def location(role: str):
                return c.execute(
                    """SELECT l.latitude,l.longitude,l.place_name FROM asset_locations al
                    JOIN locations l ON l.id=al.location_id
                    WHERE al.asset_id=? AND al.role=? ORDER BY al.precedence DESC,l.id DESC LIMIT 1""",
                    (r["id"], role),
                ).fetchone()

            capture = location("capture")
            subject = location("subject")
            return AssetDetail(
                public_id=r["public_id"],
                revision=r["revision"],
                title=r["title"],
                caption=r["caption"],
                user_notes=r["user_notes"],
                rating=r["rating"],
                color_label=r["color_label"],
                pick_state=r["pick_state"],
                primary_path=r["normalized_path"],
                mime_type=r["mime_type"],
                format_name=r["format_name"],
                pixel_width=r["pixel_width"],
                pixel_height=r["pixel_height"],
                tags=tags,
                capture_latitude=capture["latitude"] if capture else None,
                capture_longitude=capture["longitude"] if capture else None,
                capture_place_name=capture["place_name"] if capture else None,
                subject_latitude=subject["latitude"] if subject else None,
                subject_longitude=subject["longitude"] if subject else None,
                subject_place_name=subject["place_name"] if subject else None,
                storage_mode=r["storage_mode"],
                availability_state=r["availability_state"],
                source_path=(r["normalized_path"] if r["storage_mode"] == "referenced" else r["import_source_path"]),
                aperture_master_path=(r["normalized_path"] if r["storage_mode"] == "managed" else None),
            )
        finally:
            c.close()

    def update_metadata(
        self, *, public_id: str, expected_revision: int, patch: MetadataPatch, modified_at_us: int
    ) -> MetadataChangeResult:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            r = u.connection.execute(
                "SELECT revision,title,caption,user_notes,rating,color_label,pick_state FROM assets WHERE public_id=? AND lifecycle_state='active'",
                (public_id,),
            ).fetchone()
            if r is None:
                raise KeyError(public_id)
            if r["revision"] != expected_revision:
                raise RuntimeError("asset_revision_conflict")
            before = MetadataPatch(
                r["title"],
                r["caption"],
                r["user_notes"],
                r["rating"],
                r["color_label"],
                r["pick_state"],
            )
            cur = u.connection.execute(
                """UPDATE assets SET title=?,caption=?,user_notes=?,rating=?,color_label=?,pick_state=?,modified_at_us=?,revision=revision+1 WHERE public_id=? AND revision=?""",
                (
                    patch.title,
                    patch.caption,
                    patch.user_notes,
                    patch.rating,
                    patch.color_label,
                    patch.pick_state,
                    modified_at_us,
                    public_id,
                    expected_revision,
                ),
            )
            if cur.rowcount != 1:
                raise RuntimeError("asset_revision_conflict")
            u.commit()
            return MetadataChangeResult(
                public_id, expected_revision, expected_revision + 1, before, patch
            )

    @staticmethod
    def _replace_tags(
        connection: sqlite3.Connection,
        *,
        asset_id: int,
        tag_names: tuple[str, ...],
        modified_at_us: int,
    ) -> None:
        connection.execute("DELETE FROM asset_tags WHERE asset_id=? AND source='user'", (asset_id,))
        for name in tag_names:
            normalized = name.casefold()
            connection.execute(
                "INSERT OR IGNORE INTO tags(public_id,normalized_name,display_name,created_at_us) "
                "VALUES(lower(hex(randomblob(16))),?,?,?)",
                (normalized, name, modified_at_us),
            )
            tag = connection.execute(
                "SELECT id FROM tags WHERE normalized_name=?", (normalized,)
            ).fetchone()
            if tag is not None:
                connection.execute(
                    "INSERT OR IGNORE INTO asset_tags(asset_id,tag_id,source,created_at_us) VALUES(?,?,'user',?)",
                    (asset_id, tag["id"], modified_at_us),
                )

    def update_metadata_and_tags(
        self,
        *,
        public_id: str,
        expected_revision: int,
        patch: MetadataPatch,
        tag_names: tuple[str, ...],
        modified_at_us: int,
    ) -> MetadataChangeResult:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            row = u.connection.execute(
                "SELECT id,revision,title,caption,user_notes,rating,color_label,pick_state "
                "FROM assets WHERE public_id=? AND lifecycle_state='active'",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(public_id)
            if row["revision"] != expected_revision:
                raise RuntimeError("asset_revision_conflict")
            before = MetadataPatch(
                row["title"],
                row["caption"],
                row["user_notes"],
                row["rating"],
                row["color_label"],
                row["pick_state"],
            )
            cursor = u.connection.execute(
                "UPDATE assets SET title=?,caption=?,user_notes=?,rating=?,color_label=?,pick_state=?,"
                "modified_at_us=?,revision=revision+1 WHERE public_id=? AND revision=?",
                (
                    patch.title,
                    patch.caption,
                    patch.user_notes,
                    patch.rating,
                    patch.color_label,
                    patch.pick_state,
                    modified_at_us,
                    public_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("asset_revision_conflict")
            self._replace_tags(
                u.connection,
                asset_id=int(row["id"]),
                tag_names=tag_names,
                modified_at_us=modified_at_us,
            )
            u.commit()
            return MetadataChangeResult(
                public_id, expected_revision, expected_revision + 1, before, patch
            )

    def update_subject_location(
        self,
        *,
        public_id: str,
        latitude: float | None,
        longitude: float | None,
        place_name: str | None,
        modified_at_us: int,
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            asset = u.connection.execute(
                "SELECT id FROM assets WHERE public_id=? AND lifecycle_state='active'", (public_id,)
            ).fetchone()
            if asset is None:
                raise KeyError(public_id)
            existing = u.connection.execute(
                "SELECT location_id FROM asset_locations WHERE asset_id=? AND role='subject' ORDER BY precedence DESC,id DESC LIMIT 1".replace(
                    ",id DESC", ""
                ),
                (asset["id"],),
            ).fetchone()
            if latitude is None or longitude is None:
                u.connection.execute(
                    "DELETE FROM asset_locations WHERE asset_id=? AND role='subject'",
                    (asset["id"],),
                )
            else:
                if existing is None:
                    cur = u.connection.execute(
                        "INSERT INTO locations(public_id,latitude,longitude,place_name,source,created_at_us) VALUES(lower(hex(randomblob(16))),?,?,?,'user',?)",
                        (latitude, longitude, place_name, modified_at_us),
                    )
                    u.connection.execute(
                        "INSERT INTO asset_locations(asset_id,location_id,role,precedence) VALUES(?,?,'subject',100)",
                        (asset["id"], cur.lastrowid),
                    )
                else:
                    u.connection.execute(
                        "UPDATE locations SET latitude=?,longitude=?,place_name=?,source='user' WHERE id=?",
                        (latitude, longitude, place_name, existing["location_id"]),
                    )
            u.commit()

    def set_tags(
        self, *, public_ids: tuple[str, ...], tag_names: tuple[str, ...], modified_at_us: int
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            for public_id in public_ids:
                row = u.connection.execute(
                    "SELECT id FROM assets WHERE public_id=? AND lifecycle_state='active'",
                    (public_id,),
                ).fetchone()
                if row is not None:
                    self._replace_tags(
                        u.connection,
                        asset_id=int(row["id"]),
                        tag_names=tag_names,
                        modified_at_us=modified_at_us,
                    )
            u.commit()

    def update_review_batch(
        self,
        *,
        targets: tuple[BatchReviewTarget, ...],
        patch: ReviewPatch,
        modified_at_us: int,
    ) -> tuple[BatchReviewResult, ...]:
        results: list[BatchReviewResult] = []
        original_rows: list[sqlite3.Row] = []
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            for target in targets:
                row = u.connection.execute(
                    "SELECT revision,rating,color_label,pick_state FROM assets WHERE public_id=? AND lifecycle_state='active'",
                    (target.public_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(target.public_id)
                if int(row["revision"]) != target.expected_revision:
                    raise RuntimeError(f"asset_revision_conflict:{target.public_id}")
                original_rows.append(row)
            for target, row in zip(targets, original_rows, strict=False):
                cursor = u.connection.execute(
                    "UPDATE assets SET rating=?,color_label=?,pick_state=?,modified_at_us=?,revision=revision+1 "
                    "WHERE public_id=? AND revision=? AND lifecycle_state='active'",
                    (
                        patch.rating if patch.update_rating else row["rating"],
                        patch.color_label if patch.update_color_label else row["color_label"],
                        patch.pick_state if patch.update_pick_state else row["pick_state"],
                        modified_at_us,
                        target.public_id,
                        target.expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"asset_revision_conflict:{target.public_id}")
                results.append(
                    BatchReviewResult(
                        target.public_id, target.expected_revision, target.expected_revision + 1
                    )
                )
            u.commit()
        return tuple(results)
