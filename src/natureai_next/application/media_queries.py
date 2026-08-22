"""Read-only canonical queries shared by the type-specific media workspaces."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def query_media_assets(
    database_path: Path,
    *,
    asset_type: str,
    detail_table: str,
    columns: tuple[str, ...],
    search_text: str = "",
) -> tuple[dict[str, Any], ...]:
    uri = database_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        detail_columns = [
            name
            for name in columns
            if name
            not in {
                "original_filename",
                "title",
                "file_size_bytes",
                "availability_state",
                "storage_mode",
                "dimensions",
                "location",
            }
        ]
        select = [
            "a.asset_public_id",
            "a.original_filename",
            "a.title",
            "a.file_size_bytes",
            "a.availability_state",
            "COALESCE(p.policy, f.storage_mode, 'referenced') AS storage_mode",
            "f.normalized_path AS source_path",
            *[f"d.{name}" for name in detail_columns],
        ]
        if asset_type == "video":
            select.extend(["d.pixel_width", "d.pixel_height"])
        elif asset_type == "sound":
            pass
        if asset_type in {"sound", "video"}:
            select.extend(
                [
                    "COALESCE(loc.latitude,d.latitude) AS latitude",
                    "COALESCE(loc.longitude,d.longitude) AS longitude",
                    "loc.country_code",
                    "loc.admin_area_1",
                    "loc.admin_area_2",
                    "loc.locality",
                    "loc.place_name",
                ]
            )
        where = "a.asset_type=?"
        params: list[Any] = [asset_type]
        if search_text.strip():
            where += " AND (a.original_filename LIKE ? ESCAPE '\\' OR a.title LIKE ? ESCAPE '\\' OR a.description LIKE ? ESCAPE '\\')"
            escaped = (
                search_text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            params.extend([pattern, pattern, pattern])
        sql = (
            f"SELECT {', '.join(dict.fromkeys(select))} FROM library_assets a "
            f"JOIN {detail_table} d ON d.asset_public_id=a.asset_public_id "
            "LEFT JOIN file_instances f ON f.public_id=a.primary_file_public_id "
            "LEFT JOIN asset_storage_policies p ON p.asset_id=f.asset_id "
            "LEFT JOIN assets core_asset ON core_asset.public_id=a.asset_public_id "
            "LEFT JOIN asset_locations al ON al.asset_id=core_asset.id AND al.precedence=("
            "SELECT max(al2.precedence) FROM asset_locations al2 WHERE al2.asset_id=core_asset.id) "
            "LEFT JOIN locations loc ON loc.id=al.location_id "
            f"WHERE {where} ORDER BY a.updated_at_us DESC LIMIT 10000"
        )
        result = []
        for row in connection.execute(sql, params):
            item = dict(row)
            if asset_type == "video":
                width, height = item.get("pixel_width"), item.get("pixel_height")
                item["dimensions"] = f"{width} × {height}" if width and height else ""
            if asset_type in {"sound", "video"}:
                lat, lon = item.get("latitude"), item.get("longitude")
                item["location"] = (
                    f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else ""
                )
                administrative = ", ".join(
                    str(value)
                    for value in (item.get("locality"), item.get("admin_area_1"), item.get("country_code"))
                    if value
                )
                if administrative:
                    item["location"] += f" · {administrative}"
            result.append(item)
        return tuple(result)
