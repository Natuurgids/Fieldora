"""Strict browser-range translation for local map archives."""

from __future__ import annotations

import re

from natureai_next.domain.maps import MapArchiveRangeResponse
from natureai_next.ports.map_archive import MapArchiveReader

_SINGLE_BOUNDED_RANGE = re.compile(r"bytes=(0|[1-9][0-9]*)-(0|[1-9][0-9]*)\Z")


class MapArchiveRangeService:
    """Translate one bounded HTTP-style range without exposing filesystem paths."""

    def __init__(self, reader: MapArchiveReader) -> None:
        self._reader = reader

    def serve(self, package_public_id: str, range_header: str) -> MapArchiveRangeResponse:
        match = _SINGLE_BOUNDED_RANGE.fullmatch(range_header.strip())
        if match is None:
            raise ValueError("map archive request requires one explicit bytes=start-end range")
        start = int(match.group(1))
        end = int(match.group(2))
        if end < start:
            raise ValueError("map archive range end cannot precede its start")

        archive_slice = self._reader.read(package_public_id, start, end - start + 1)
        actual_end = archive_slice.offset + len(archive_slice.data) - 1
        return MapArchiveRangeResponse(
            status_code=206,
            content_range=f"bytes {archive_slice.offset}-{actual_end}/{archive_slice.total_size}",
            accept_ranges="bytes",
            content_length=len(archive_slice.data),
            media_type=archive_slice.media_type,
            data=archive_slice.data,
            checksum_sha256=archive_slice.checksum_sha256,
        )
