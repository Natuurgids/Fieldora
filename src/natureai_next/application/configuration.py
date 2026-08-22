"""Typed configuration models and scope-aware effective settings."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from pathlib import Path
from typing import Self, TypeVar, get_type_hints

CURRENT_CONFIG_SCHEMA_VERSION = 1
T = TypeVar("T")


class Theme(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class UpdateCheckPolicy(StrEnum):
    MANUAL = "manual"
    STARTUP = "startup"
    SCHEDULED = "scheduled"
    DISABLED = "disabled"


class ExecutionProvider(StrEnum):
    AUTO = "auto"
    CUDA = "cuda"
    CPU = "cpu"
    ONNX_CUDA = "onnx_cuda"
    ONNX_CPU = "onnx_cpu"


class StorageMode(StrEnum):
    MANAGED = "managed"
    REFERENCED = "referenced"
    HYBRID = "hybrid"


class DuplicatePolicy(StrEnum):
    SKIP = "skip"
    LINK = "link"
    IMPORT_SEPARATE = "import_separate"


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    interface_language: str = "en"
    theme: Theme = Theme.SYSTEM
    update_check_policy: UpdateCheckPolicy = UpdateCheckPolicy.MANUAL
    recent_libraries_limit: int = 10
    log_level: LogLevel = LogLevel.INFO
    log_retention_days: int = 30
    crash_recovery_enabled: bool = True
    developer_mode: bool = False

    def validate(self) -> None:
        if not 1 <= self.recent_libraries_limit <= 100:
            raise ValueError("recent_libraries_limit must be between 1 and 100")
        if not 1 <= self.log_retention_days <= 3650:
            raise ValueError("log_retention_days must be between 1 and 3650")
        if not self.interface_language.strip():
            raise ValueError("interface_language must not be blank")


@dataclass(frozen=True, slots=True)
class PerformanceSettings:
    io_workers: int = 4
    cpu_workers: int = 4
    thumbnail_memory_cache_mib: int = 512
    thumbnail_disk_cache_mib: int = 8192
    database_cache_mib: int = 256
    job_batch_size: int = 128
    vector_search_candidates: int = 200

    @classmethod
    def hardware_defaults(cls) -> Self:
        cpu_count = os.cpu_count() or 4
        return cls(
            io_workers=min(8, max(2, cpu_count // 2)), cpu_workers=min(12, max(2, cpu_count - 2))
        )

    def validate(self) -> None:
        limits = {
            "io_workers": (1, 32),
            "cpu_workers": (1, 64),
            "thumbnail_memory_cache_mib": (64, 8192),
            "thumbnail_disk_cache_mib": (512, 262144),
            "database_cache_mib": (32, 8192),
            "job_batch_size": (1, 4096),
            "vector_search_candidates": (10, 10000),
        }
        for name, (minimum, maximum) in limits.items():
            value = getattr(self, name)
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True, slots=True)
class AISettings:
    preferred_provider: ExecutionProvider = ExecutionProvider.AUTO
    gpu_device: int = 0
    vram_budget_mib: int = 6144
    model_idle_unload_seconds: int = 300
    automatic_embedding_on_import: bool = False

    def validate(self) -> None:
        if not 0 <= self.gpu_device <= 31:
            raise ValueError("gpu_device must be between 0 and 31")
        if not 512 <= self.vram_budget_mib <= 65536:
            raise ValueError("vram_budget_mib must be between 512 and 65536")
        if not 0 <= self.model_idle_unload_seconds <= 86400:
            raise ValueError("model_idle_unload_seconds must be between 0 and 86400")


@dataclass(frozen=True, slots=True)
class ImportSettings:
    default_storage_mode: StorageMode = StorageMode.MANAGED
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.SKIP
    preserve_folder_hierarchy: bool = True
    queue_ai_after_import: bool = False

    def validate(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class PluginSettings:
    enabled_plugin_ids: tuple[str, ...] = ()
    trusted_publishers_only: bool = True
    development_paths: tuple[Path, ...] = ()

    def validate(self) -> None:
        if len(set(self.enabled_plugin_ids)) != len(self.enabled_plugin_ids):
            raise ValueError("enabled_plugin_ids must not contain duplicates")


@dataclass(frozen=True, slots=True)
class Settings:
    schema_version: int
    application: ApplicationSettings
    performance: PerformanceSettings
    ai: AISettings
    imports: ImportSettings
    plugins: PluginSettings

    @classmethod
    def defaults(cls) -> Self:
        return cls(
            schema_version=CURRENT_CONFIG_SCHEMA_VERSION,
            application=ApplicationSettings(),
            performance=PerformanceSettings.hardware_defaults(),
            ai=AISettings(),
            imports=ImportSettings(),
            plugins=PluginSettings(),
        )

    def validate(self) -> None:
        if self.schema_version != CURRENT_CONFIG_SCHEMA_VERSION:
            raise ValueError(f"Unsupported configuration schema version: {self.schema_version}")
        self.application.validate()
        self.performance.validate()
        self.ai.validate()
        self.imports.validate()
        self.plugins.validate()


@dataclass(frozen=True, slots=True)
class EffectiveValue:
    key: str
    value: object
    source: str


@dataclass(frozen=True, slots=True)
class EffectiveSettings:
    settings: Settings
    sources: Mapping[str, str]
    unknown: Mapping[str, object]

    def describe(self) -> tuple[EffectiveValue, ...]:
        values: list[EffectiveValue] = []
        for section_field in fields(self.settings):
            section = getattr(self.settings, section_field.name)
            if not hasattr(section, "__dataclass_fields__"):
                key = section_field.name
                values.append(EffectiveValue(key, section, self.sources.get(key, "defaults")))
                continue
            for item in fields(section):
                key = f"{section_field.name}.{item.name}"
                values.append(
                    EffectiveValue(
                        key, getattr(section, item.name), self.sources.get(key, "defaults")
                    )
                )
        return tuple(values)


def merge_dataclass(instance: T, values: Mapping[str, object]) -> T:
    hints = get_type_hints(type(instance))
    updates: dict[str, object] = {}
    known = {field.name for field in fields(instance)}
    for key, value in values.items():
        if key not in known:
            continue
        target = hints[key]
        updates[key] = _coerce_value(target, value)
    return replace(instance, **updates)


def _coerce_value(target: object, value: object) -> object:
    if isinstance(target, type) and issubclass(target, StrEnum):
        return target(value)
    if target == tuple[str, ...]:
        if not isinstance(value, list | tuple):
            raise TypeError("expected a list of strings")
        return tuple(str(item) for item in value)
    if target == tuple[Path, ...]:
        if not isinstance(value, list | tuple):
            raise TypeError("expected a list of paths")
        return tuple(Path(str(item)) for item in value)
    if target is Path:
        return Path(str(value))
    if target in {str, int, bool, float} and type(value) is not target:
        raise TypeError(f"expected {target.__name__}, got {type(value).__name__}")
    return value
