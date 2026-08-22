"""Production standard-library implementations of basic system ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SystemUuidGenerator:
    def new_uuid(self) -> UUID:
        return uuid4()
