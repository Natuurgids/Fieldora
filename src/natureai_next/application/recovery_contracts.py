"""Common recovery vocabulary for subsystem-owned recovery implementations."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RecoveryState(StrEnum):
    READY = "ready"
    RECOVERING = "recovering"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    provider: str
    state: RecoveryState
    recovered: int = 0
    skipped: int = 0
    messages: tuple[str, ...] = ()


class RecoveryService(Protocol):
    def recover(self) -> RecoveryResult: ...
    def verify(self) -> RecoveryResult: ...
    def cleanup(self, *, preview: bool = True) -> RecoveryResult: ...
