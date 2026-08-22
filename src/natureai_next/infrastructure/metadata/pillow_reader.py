"""Bounded normalized metadata extraction using Pillow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

from natureai_next.ports.media import MetadataResult


class PillowMetadataReader:
    def __init__(self, *, max_entries: int = 512, max_text_length: int = 4096) -> None:
        self.max_entries = max_entries
        self.max_text_length = max_text_length

    def read(self, path: Path) -> MetadataResult:
        try:
            with Image.open(path) as image:
                exif = image.getexif()
                raw: dict[str, object] = {}
                warnings: list[str] = []
                for index, (tag_id, value) in enumerate(exif.items()):
                    if index >= self.max_entries:
                        warnings.append("metadata_entry_limit_reached")
                        break
                    name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    raw[name] = self._safe_value(value)
                gps = self._read_gps(exif, warnings)
                if gps:
                    raw["GPSInfo"] = gps
                normalized = {
                    "pixel_width": image.width,
                    "pixel_height": image.height,
                    "format_name": image.format,
                    "orientation": raw.get("Orientation"),
                    "camera_make": raw.get("Make"),
                    "camera_model": raw.get("Model"),
                    "lens": raw.get("LensModel"),
                    "capture_time_text": raw.get("DateTimeOriginal") or raw.get("DateTime"),
                    "capture_latitude": gps.get("latitude") if gps else None,
                    "capture_longitude": gps.get("longitude") if gps else None,
                    "capture_altitude_m": gps.get("altitude_m") if gps else None,
                    "location_source": "exif_gps"
                    if gps and gps.get("latitude") is not None
                    else None,
                }
                return MetadataResult(normalized, raw, tuple(warnings))
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise ValueError(f"cannot read image metadata: {path}") from exc

    def _read_gps(self, exif: Any, warnings: list[str]) -> dict[str, object]:
        gps_tag = next((tag for tag, name in ExifTags.TAGS.items() if name == "GPSInfo"), 34853)
        try:
            values = exif.get_ifd(gps_tag)
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}
        if not values:
            return {}
        named = {ExifTags.GPSTAGS.get(key, str(key)): value for key, value in values.items()}
        try:
            latitude = _coordinate(named.get("GPSLatitude"), named.get("GPSLatitudeRef"))
            longitude = _coordinate(named.get("GPSLongitude"), named.get("GPSLongitudeRef"))
            altitude = _ratio(named.get("GPSAltitude"))
            if altitude is not None and int(named.get("GPSAltitudeRef") or 0) == 1:
                altitude = -altitude
        except (TypeError, ValueError, ZeroDivisionError):
            warnings.append("invalid_gps_metadata")
            return {}
        result: dict[str, object] = {}
        if latitude is not None and longitude is not None:
            result.update(latitude=latitude, longitude=longitude)
        if altitude is not None:
            result["altitude_m"] = altitude
        return result

    def _safe_value(self, value: object) -> object:
        if isinstance(value, bytes):
            return value[: self.max_text_length].hex()
        text = str(value)
        return text if len(text) <= self.max_text_length else text[: self.max_text_length]


def _ratio(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _coordinate(value: object, reference: object) -> float | None:
    if not value or not reference:
        return None
    parts = tuple(float(part) for part in value)  # type: ignore[arg-type]
    if len(parts) != 3:
        return None
    coordinate = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
    ref = str(reference).upper()
    if ref in {"S", "W"}:
        coordinate = -coordinate
    return coordinate
