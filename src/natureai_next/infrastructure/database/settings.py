"""SQLite adapter settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SqliteSettings:
    busy_timeout_ms: int = 5000
    synchronous: str = "NORMAL"
    cache_size_kib: int = 65536
    mmap_size_bytes: int = 268435456

    def __post_init__(self) -> None:
        if self.busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        if self.synchronous not in {"NORMAL", "FULL"}:
            raise ValueError("synchronous must be NORMAL or FULL")
        if self.cache_size_kib < 1024:
            raise ValueError("cache_size_kib must be at least 1024")
