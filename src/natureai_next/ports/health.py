"""Health assessment adapter contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.subsystems import SubsystemState


class IntegrityReportView(Protocol):
    healthy: bool
    quick_check: tuple[str, ...]
    foreign_key_violations: tuple[object, ...]
    messages: tuple[str, ...]


class ConnectionFactory(Protocol):
    def connect(self, *, read_only: bool = False) -> None: ...


class SubsystemStatusView(Protocol):
    state: SubsystemState
    database_path: Path
    schema_version: int
    message: str


class SubsystemDescriptorView(Protocol):
    schema_version: int


class SubsystemHealthRegistry(Protocol):
    def keys(self) -> tuple[str, ...]: ...
    def status(self, key: str, *, run_integrity_check: bool = False) -> SubsystemStatusView: ...
    def descriptor(self, key: str) -> SubsystemDescriptorView: ...
