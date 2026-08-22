"""Typed, stable, user-safe application error model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    CONFIG_INVALID = "configuration.invalid"
    CONFIG_READ_FAILED = "configuration.read_failed"
    CONFIG_WRITE_FAILED = "configuration.write_failed"
    CONFIG_MIGRATION_FAILED = "configuration.migration_failed"
    PLUGIN_MANIFEST_INVALID = "plugin.manifest_invalid"
    PLUGIN_INCOMPATIBLE = "plugin.incompatible"
    PLUGIN_CAPABILITY_DENIED = "plugin.capability_denied"
    INTERNAL_UNEXPECTED = "internal.unexpected"


class Retryability(StrEnum):
    NEVER = "never"
    TRANSIENT = "transient"
    USER_ACTION = "user_action"


@dataclass(frozen=True, slots=True)
class ErrorDescriptor:
    code: ErrorCode
    summary: str
    retryability: Retryability = Retryability.NEVER
    technical_detail: str | None = None
    entity_ids: tuple[str, ...] = ()
    remediation: str | None = None
    context: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


class NatureAIError(Exception):
    """Base exception carrying a stable descriptor."""

    def __init__(self, descriptor: ErrorDescriptor) -> None:
        super().__init__(descriptor.summary)
        self.descriptor = descriptor


class ConfigurationError(NatureAIError):
    """Configuration loading, validation, migration, or persistence failure."""


class PluginError(NatureAIError):
    """Plugin discovery, compatibility, registration, or activation failure."""
