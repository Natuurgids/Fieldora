"""Port for loading user-selected GPS track files."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.maps import GpsTrack


class GpsTrackLoader(Protocol):
    def load(self, path: Path) -> GpsTrack: ...
