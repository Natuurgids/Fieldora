"""Canonical media location editing and administrative reverse geocoding."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class AdministrativeLocation:
    country_code: str | None = None
    admin_area_1: str | None = None
    admin_area_2: str | None = None
    locality: str | None = None
    place_name: str | None = None


class ReverseGeocoder(Protocol):
    def reverse(self, latitude: float, longitude: float) -> AdministrativeLocation: ...


class NominatimReverseGeocoder:
    """Small standards-based client for the public OpenStreetMap reverse endpoint."""

    endpoint = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds

    def reverse(self, latitude: float, longitude: float) -> AdministrativeLocation:
        query = urlencode(
            {
                "format": "jsonv2",
                "lat": f"{latitude:.7f}",
                "lon": f"{longitude:.7f}",
                "zoom": "10",
                "addressdetails": "1",
            }
        )
        request = Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": "Fieldora/0.11 location-reporting (desktop application)"},
        )
        with urlopen(request, timeout=self._timeout) as response:  # noqa: S310 - fixed HTTPS endpoint
            payload = json.load(response)
        address = payload.get("address") or {}
        country_code = _clean(address.get("country_code"))
        return AdministrativeLocation(
            country_code=country_code.upper() if country_code else None,
            admin_area_1=_first(address, "state", "province", "region"),
            admin_area_2=_first(address, "county", "state_district"),
            locality=_first(address, "city", "town", "village", "municipality", "hamlet"),
            place_name=_clean(payload.get("display_name")),
        )


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    examined: int
    resolved: int
    failed: int


class MediaLocationEnrichmentService:
    """Keeps media detail coordinates and canonical report locations synchronized."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def save(
        self,
        *,
        asset_public_id: str,
        media_type: str,
        latitude: float,
        longitude: float,
        administrative: AdministrativeLocation | None = None,
    ) -> None:
        _validate_coordinates(latitude, longitude)
        if media_type not in {"photo", "sound", "video", "document"}:
            raise ValueError(f"unsupported media type: {media_type}")
        administrative = administrative or AdministrativeLocation()
        with sqlite3.connect(self._database_path, timeout=10.0) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            asset = connection.execute(
                "SELECT id FROM assets WHERE public_id=? AND lifecycle_state='active'",
                (asset_public_id,),
            ).fetchone()
            if asset is None:
                raise KeyError(asset_public_id)
            location = connection.execute(
                """SELECT l.id FROM asset_locations al JOIN locations l ON l.id=al.location_id
                   WHERE al.asset_id=? AND al.role='capture'
                   ORDER BY al.precedence DESC,l.id DESC LIMIT 1""",
                (asset["id"],),
            ).fetchone()
            values = (
                latitude,
                longitude,
                _clean(administrative.country_code, upper=True),
                _clean(administrative.admin_area_1),
                _clean(administrative.admin_area_2),
                _clean(administrative.locality),
                _clean(administrative.place_name),
            )
            if location is None:
                cursor = connection.execute(
                    """INSERT INTO locations(
                       public_id,latitude,longitude,country_code,admin_area_1,admin_area_2,
                       locality,place_name,source,created_at_us)
                       VALUES(lower(hex(randomblob(16))),?,?,?,?,?,?,?,'location_enrichment',?)""",
                    (*values, time.time_ns() // 1000),
                )
                connection.execute(
                    "INSERT INTO asset_locations(asset_id,location_id,role,precedence) VALUES(?,?,'capture',110)",
                    (asset["id"], cursor.lastrowid),
                )
            else:
                connection.execute(
                    """UPDATE locations SET latitude=?,longitude=?,country_code=?,admin_area_1=?,
                       admin_area_2=?,locality=?,place_name=?,source='location_enrichment' WHERE id=?""",
                    (*values, location["id"]),
                )
            if media_type in {"sound", "video"}:
                connection.execute(
                    f"UPDATE {media_type}_assets SET latitude=?,longitude=? WHERE asset_public_id=?",
                    (latitude, longitude, asset_public_id),
                )

    def reverse_asset(
        self, asset_public_id: str, *, geocoder: ReverseGeocoder | None = None
    ) -> AdministrativeLocation:
        geocoder = geocoder or NominatimReverseGeocoder()
        row = self._coordinate_row(asset_public_id)
        if row is None:
            raise ValueError("asset has no latitude and longitude")
        result = geocoder.reverse(float(row["latitude"]), float(row["longitude"]))
        self.save(
            asset_public_id=asset_public_id,
            media_type=str(row["media_type"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            administrative=result,
        )
        return result

    def reconstruct_missing(
        self,
        *,
        asset_public_ids: tuple[str, ...] | None = None,
        geocoder: ReverseGeocoder | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        request_interval_seconds: float = 1.05,
    ) -> ReconstructionResult:
        geocoder = geocoder or NominatimReverseGeocoder()
        rows = self._missing_rows(asset_public_ids)
        resolved = failed = 0
        cache: dict[tuple[float, float], AdministrativeLocation] = {}
        for index, row in enumerate(rows, 1):
            if cancelled and cancelled():
                raise InterruptedError
            if progress:
                progress(index - 1, len(rows), f"Resolving {row['asset_public_id']}")
            key = (round(float(row["latitude"]), 4), round(float(row["longitude"]), 4))
            try:
                result = cache.get(key)
                if result is None:
                    result = geocoder.reverse(float(row["latitude"]), float(row["longitude"]))
                    cache[key] = result
                    if request_interval_seconds > 0 and index < len(rows):
                        time.sleep(request_interval_seconds)
                self.save(
                    asset_public_id=str(row["asset_public_id"]),
                    media_type=str(row["media_type"]),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    administrative=result,
                )
                resolved += 1
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                failed += 1
        if progress:
            progress(len(rows), len(rows), "Location reconstruction complete")
        return ReconstructionResult(len(rows), resolved, failed)

    def _coordinate_row(self, asset_public_id: str):
        rows = self._coordinate_rows((asset_public_id,), missing_only=False)
        return rows[0] if rows else None

    def _missing_rows(self, asset_public_ids: tuple[str, ...] | None):
        return self._coordinate_rows(asset_public_ids, missing_only=True)

    def _coordinate_rows(self, asset_public_ids, *, missing_only: bool):
        params: list[object] = []
        scope = ""
        if asset_public_ids is not None:
            if not asset_public_ids:
                return ()
            scope = f" AND a.public_id IN ({','.join('?' for _ in asset_public_ids)})"
            params.extend(asset_public_ids)
        missing = " AND (l.country_code IS NULL OR trim(l.country_code)='' OR l.admin_area_1 IS NULL OR trim(l.admin_area_1)='')" if missing_only else ""
        with sqlite3.connect(self._database_path, timeout=10.0) as connection:
            connection.row_factory = sqlite3.Row
            return tuple(
                connection.execute(
                    """SELECT a.public_id asset_public_id,a.media_type,
                       COALESCE(l.latitude,sa.latitude,va.latitude) latitude,
                       COALESCE(l.longitude,sa.longitude,va.longitude) longitude
                       FROM assets a
                       LEFT JOIN asset_locations al ON al.asset_id=a.id AND al.precedence=(
                           SELECT max(al2.precedence) FROM asset_locations al2 WHERE al2.asset_id=a.id)
                       LEFT JOIN locations l ON l.id=al.location_id
                       LEFT JOIN sound_assets sa ON sa.asset_public_id=a.public_id
                       LEFT JOIN video_assets va ON va.asset_public_id=a.public_id
                       WHERE a.lifecycle_state='active'
                       AND COALESCE(l.latitude,sa.latitude,va.latitude) IS NOT NULL
                       AND COALESCE(l.longitude,sa.longitude,va.longitude) IS NOT NULL"""
                    + missing
                    + scope
                    + " ORDER BY a.id",
                    params,
                )
            )


def _clean(value: object, *, upper: bool = False) -> str | None:
    text = str(value).strip() if value is not None else ""
    return (text.upper() if upper else text) or None


def _first(values: dict, *keys: str) -> str | None:
    return next((_clean(values.get(key)) for key in keys if _clean(values.get(key))), None)


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
