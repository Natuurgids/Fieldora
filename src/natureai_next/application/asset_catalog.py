from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw'}
_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.oga', '.m4a', '.aac', '.wma', '.aiff', '.aif'}
_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.mpeg', '.mpg'}
_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.md', '.csv', '.xls', '.xlsx', '.ods', '.ppt', '.pptx'}
_MAP_EXTENSIONS = {'.shp', '.shx', '.dbf', '.gpkg', '.geojson', '.kml', '.kmz', '.gpx', '.mbtiles', '.pmtiles', '.tif', '.tiff', '.vrt', '.asc', '.las', '.laz'}
_ARCHIVE_EXTENSIONS = {'.zip', '.7z', '.tar', '.gz', '.tgz', '.bz2', '.xz'}


def classify_asset_type(
    *,
    mime_type: str | None,
    path: str | None,
    media_type: str | None,
    catalog_type: str | None = None,
) -> str:
    """Return the canonical asset class without trusting legacy image-only fields."""
    catalog = str(catalog_type or '').strip().casefold()
    aliases = {
        'image': 'photo', 'photo': 'photo', 'photograph': 'photo',
        'audio': 'sound', 'sound': 'sound', 'recording': 'sound',
        'movie': 'video', 'video': 'video',
        'pdf': 'document', 'document': 'document', 'text': 'document', 'spreadsheet': 'document',
        'map': 'map', 'gis': 'map', 'raster': 'map', 'vector': 'map',
        'archive': 'archive',
    }
    if catalog in aliases:
        return aliases[catalog]

    mime = str(mime_type or '').split(';', 1)[0].strip().casefold()
    if mime.startswith('audio/'):
        return 'sound'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('image/'):
        # GeoTIFF and other mapped rasters are resolved by extension below.
        extension = Path(str(path or '')).suffix.casefold()
        if extension in _MAP_EXTENSIONS:
            return 'map'
        return 'photo'
    if mime in {
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    } or mime.startswith('text/'):
        return 'document'
    if mime in {'application/geopackage+sqlite3', 'application/geo+json', 'application/vnd.google-earth.kml+xml'}:
        return 'map'
    if mime in {'application/zip', 'application/x-7z-compressed', 'application/x-tar', 'application/gzip'}:
        return 'archive'

    extension = Path(str(path or '')).suffix.casefold()
    if extension in _MAP_EXTENSIONS:
        return 'map'
    if extension in _IMAGE_EXTENSIONS:
        return 'photo'
    if extension in _AUDIO_EXTENSIONS:
        return 'sound'
    if extension in _VIDEO_EXTENSIONS:
        return 'video'
    if extension in _DOCUMENT_EXTENSIONS:
        return 'document'
    if extension in _ARCHIVE_EXTENSIONS:
        return 'archive'

    legacy = str(media_type or '').strip().casefold()
    return aliases.get(legacy, legacy or 'other')


@dataclass(frozen=True)
class AssetSummary:
    asset_id: str
    asset_type: str
    title: str
    captured: str
    rating: str
    path: str
    mime_type: str
    file_size: int


class AssetCatalogService:
    """Read-only unified catalogue over legacy assets and typed library metadata."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def _has_table(self, connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    def list_assets(self, *, asset_type: str = 'all', search: str = '', limit: int = 200, offset: int = 0) -> list[AssetSummary]:
        with sqlite3.connect(self.database) as connection:
            has_library_assets = self._has_table(connection, 'library_assets')
            catalog_join = (
                'LEFT JOIN library_assets la ON la.asset_public_id=a.public_id'
                if has_library_assets else ''
            )
            catalog_column = 'la.asset_type' if has_library_assets else "''"
            rows = connection.execute(
                f"""
                SELECT a.public_id,COALESCE(a.title,''),COALESCE(a.capture_local_text,''),
                       COALESCE(a.rating,''),COALESCE(f.normalized_path,''),COALESCE(f.mime_type,''),
                       COALESCE(f.file_size,0),COALESCE(a.media_type,''),COALESCE({catalog_column},'')
                  FROM assets a
                  LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                  {catalog_join}
                 WHERE a.lifecycle_state='active'
                 ORDER BY a.modified_at_us DESC
                 LIMIT ? OFFSET ?
                """,
                (int(limit), max(0, int(offset))),
            ).fetchall()

        wanted = asset_type.casefold().strip()
        query = search.casefold().strip()
        result: list[AssetSummary] = []
        for asset_id, title, captured, rating, path, mime, size, legacy_type, catalog_type in rows:
            kind = classify_asset_type(
                mime_type=mime, path=path, media_type=legacy_type, catalog_type=catalog_type
            )
            if wanted not in {'', 'all'}:
                if wanted == 'other':
                    if kind in {'photo', 'sound', 'video', 'document', 'map'}:
                        continue
                elif kind != wanted:
                    continue
            display_title = str(title or Path(str(path or '')).name or asset_id)
            haystack = ' '.join((display_title, str(path), str(mime), str(kind), str(asset_id))).casefold()
            if query and query not in haystack:
                continue
            result.append(AssetSummary(
                asset_id=str(asset_id), asset_type=kind, title=display_title,
                captured=str(captured or ''), rating=str(rating or ''), path=str(path or ''),
                mime_type=str(mime or ''), file_size=int(size or 0),
            ))
        return result


    def count_assets(self, *, search: str = '') -> int:
        """Return the active catalogue size without materialising asset rows."""
        query = str(search or '').strip().casefold()
        with sqlite3.connect(self.database) as connection:
            if not query:
                row = connection.execute(
                    "SELECT COUNT(*) FROM assets WHERE lifecycle_state='active'"
                ).fetchone()
                return int(row[0] if row else 0)
            pattern = f"%{query}%"
            row = connection.execute(
                """SELECT COUNT(*)
                     FROM assets a
                     LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                    WHERE a.lifecycle_state='active'
                      AND (LOWER(COALESCE(a.title,'')) LIKE ?
                           OR LOWER(COALESCE(f.normalized_path,'')) LIKE ?
                           OR LOWER(COALESCE(f.mime_type,'')) LIKE ?
                           OR LOWER(COALESCE(a.public_id,'')) LIKE ?)""",
                (pattern, pattern, pattern, pattern),
            ).fetchone()
            return int(row[0] if row else 0)

    def asset_type(self, asset_id: str) -> str:
        with sqlite3.connect(self.database) as connection:
            has_library_assets = self._has_table(connection, 'library_assets')
            catalog_join = (
                'LEFT JOIN library_assets la ON la.asset_public_id=a.public_id'
                if has_library_assets else ''
            )
            catalog_column = 'la.asset_type' if has_library_assets else "''"
            row = connection.execute(
                f"""SELECT COALESCE(f.mime_type,''),COALESCE(f.normalized_path,''),
                           COALESCE(a.media_type,''),COALESCE({catalog_column},'')
                      FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                      {catalog_join} WHERE a.public_id=?""",
                (asset_id,),
            ).fetchone()
        if row is None:
            return 'other'
        return classify_asset_type(mime_type=row[0], path=row[1], media_type=row[2], catalog_type=row[3])

    def relationships(self, asset_id: str) -> list[tuple[str, str]]:
        links: list[tuple[str, str]] = []
        with sqlite3.connect(self.database) as connection:
            asset_row = connection.execute('SELECT id FROM assets WHERE public_id=?', (asset_id,)).fetchone()
            if asset_row is None:
                return links
            internal_id = asset_row[0]
            if self._has_table(connection, 'observations'):
                links.extend(('Observation', str(row[0])) for row in connection.execute(
                    'SELECT public_id FROM observations WHERE asset_id=? ORDER BY modified_at_us DESC',
                    (internal_id,),
                ).fetchall())
            if self._has_table(connection, 'collection_assets') and self._has_table(connection, 'collections'):
                links.extend(('Collection', str(row[0])) for row in connection.execute(
                    '''SELECT c.name FROM collection_assets ca JOIN collections c ON c.id=ca.collection_id
                       WHERE ca.asset_id=? ORDER BY c.name''', (internal_id,)
                ).fetchall())
            if self._has_table(connection, 'asset_tags') and self._has_table(connection, 'tags'):
                links.extend(('Tag', str(row[0])) for row in connection.execute(
                    '''SELECT t.display_name FROM asset_tags at JOIN tags t ON t.id=at.tag_id
                       WHERE at.asset_id=? ORDER BY t.display_name''', (internal_id,)
                ).fetchall())
        return links
