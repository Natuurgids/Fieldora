"""Port for bounded reads from renderer-owned map archives."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.maps import MapArchiveSlice


class MapArchiveReader(Protocol):
    def read(self, package_public_id: str, offset: int, length: int) -> MapArchiveSlice: ...
