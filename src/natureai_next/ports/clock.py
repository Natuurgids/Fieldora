"""Clock abstraction for deterministic application behavior."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now_utc(self) -> datetime:
        """Return a timezone-aware UTC instant."""
