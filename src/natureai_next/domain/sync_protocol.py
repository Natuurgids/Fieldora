"""Versioned Phase E pull/push protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from natureai_next.domain.synchronization import SyncChange

SYNC_PROTOCOL_VERSION = 1


class PushDisposition(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class PushResult:
    change_id: str
    disposition: PushDisposition
    remote_revision: int = 0
    remote_payload: dict[str, object] | None = None
    retry_at_utc: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PullPage:
    enrollment_id: str
    changes: tuple[SyncChange, ...]
    next_cursor: str
    has_more: bool
    protocol_version: int = SYNC_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != SYNC_PROTOCOL_VERSION:
            raise ValueError("unsupported synchronization protocol version")
        if self.has_more and not self.next_cursor:
            raise ValueError("a non-terminal pull page requires a cursor")

