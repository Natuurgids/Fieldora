"""Bounded GPX 1.0/1.1 track-file adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from natureai_next.domain.maps import GpsTrack, GpsTrackPoint


class GpxTrackLoader:
    MAX_BYTES = 32 * 1024 * 1024
    MAX_POINTS = 500_000

    def load(self, path: Path) -> GpsTrack:
        if path.suffix.casefold() != ".gpx":
            raise ValueError("GPS track must use the .gpx extension")
        size = path.stat().st_size
        if size <= 0 or size > self.MAX_BYTES:
            raise ValueError("GPX file is empty or exceeds the 32 MiB safety limit")
        payload = path.read_bytes()
        lowered = payload.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise ValueError("GPX document types and entities are not supported")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError("GPX file is not well-formed XML") from exc
        if self._local_name(root.tag) != "gpx":
            raise ValueError("file does not contain a GPX document")
        name = path.stem
        for element in root.iter():
            if self._local_name(element.tag) == "name" and element.text and element.text.strip():
                name = element.text.strip()[:200]
                break
        segments: list[tuple[GpsTrackPoint, ...]] = []
        total = 0
        for segment in (item for item in root.iter() if self._local_name(item.tag) == "trkseg"):
            points: list[GpsTrackPoint] = []
            for item in segment:
                if self._local_name(item.tag) != "trkpt":
                    continue
                latitude = self._coordinate(item.attrib.get("lat"), -90.0, 90.0, "latitude")
                longitude = self._coordinate(item.attrib.get("lon"), -180.0, 180.0, "longitude")
                elevation = None
                recorded_at = None
                for child in item:
                    local = self._local_name(child.tag)
                    if local == "ele" and child.text:
                        try:
                            elevation = float(child.text.strip())
                        except ValueError:
                            elevation = None
                    elif local == "time" and child.text:
                        recorded_at = child.text.strip()[:80]
                points.append(GpsTrackPoint(latitude, longitude, elevation, recorded_at))
                total += 1
                if total > self.MAX_POINTS:
                    raise ValueError("GPX file exceeds the 500,000-point safety limit")
            if points:
                segments.append(tuple(points))
        if not segments:
            raise ValueError("GPX file contains no track points")
        return GpsTrack(name, tuple(segments))

    @staticmethod
    def _coordinate(value: str | None, minimum: float, maximum: float, label: str) -> float:
        try:
            coordinate = float(value or "")
        except ValueError as exc:
            raise ValueError(f"GPX track point has an invalid {label}") from exc
        if not minimum <= coordinate <= maximum:
            raise ValueError(f"GPX track point {label} is outside the valid range")
        return coordinate

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].casefold()
