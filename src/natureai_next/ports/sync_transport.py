"""Transport boundary for the versioned desktop synchronization protocol."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.sync_protocol import PullPage, PushResult
from natureai_next.domain.synchronization import SyncChange


class SynchronizationTransport(Protocol):
    def push(
        self, *, enrollment_id: str, changes: tuple[SyncChange, ...]
    ) -> tuple[PushResult, ...]: ...

    def pull(
        self, *, enrollment_id: str, cursor: str, limit: int
    ) -> PullPage: ...

