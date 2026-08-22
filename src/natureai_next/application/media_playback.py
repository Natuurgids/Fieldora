"""Producer-neutral playback state shared by concrete media viewers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TemporalPlaybackBinding:
    """Clamp and convert media positions without depending on Qt multimedia."""

    asset_id: str | None = None
    duration_ms: int = 0
    position_ms: int = 0

    def load(self, asset_id: str, duration_ms: int | None = None) -> None:
        self.asset_id = str(asset_id)
        self.duration_ms = max(0, int(duration_ms or 0))
        self.position_ms = 0

    def update_duration(self, duration_ms: int) -> int:
        self.duration_ms = max(0, int(duration_ms))
        self.position_ms = self._clamp(self.position_ms)
        return self.duration_ms

    def seek_seconds(self, seconds: float) -> int:
        self.position_ms = self._clamp(round(max(0.0, float(seconds)) * 1000.0))
        return self.position_ms

    def update_position(self, position_ms: int) -> float:
        self.position_ms = self._clamp(int(position_ms))
        return self.position_ms / 1000.0

    def _clamp(self, value: int) -> int:
        value = max(0, value)
        return min(value, self.duration_ms) if self.duration_ms > 0 else value
