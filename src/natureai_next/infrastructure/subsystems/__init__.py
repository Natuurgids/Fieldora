"""Lazy optional-subsystem database support."""

from natureai_next.infrastructure.subsystems.registry import (
    SubsystemDatabaseDescriptor,
    SubsystemDatabaseRegistry,
    SubsystemHealth,
    SubsystemState,
)

__all__ = [
    "SubsystemDatabaseDescriptor",
    "SubsystemDatabaseRegistry",
    "SubsystemHealth",
    "SubsystemState",
]
