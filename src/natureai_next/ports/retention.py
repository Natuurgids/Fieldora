"""Persistence contract for bounded workflow-history cleanup."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.workflows import RetentionPolicy


class RetentionHistoryStore(Protocol):
    def eligible_ids(
        self, *, now_us: int, policy: RetentionPolicy
    ) -> tuple[tuple[int, ...], tuple[int, ...]]: ...

    def delete(self, *, job_ids: tuple[int, ...], event_ids: tuple[int, ...]) -> None: ...
