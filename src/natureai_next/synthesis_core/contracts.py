"""Stable execution boundary between replaceable engines and Aperture."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from natureai_next.domain.enrichment import CanonicalCandidate


class ExtensionKind(StrEnum):
    CAPABILITY = "capability"
    SOURCE = "source"


class InputKind(StrEnum):
    PHOTO = "photo"
    SOUND = "sound"
    VIDEO = "video"
    DOCUMENT = "document"
    STRUCTURED = "structured"


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    capability_id: str
    subject_public_id: str
    input_kind: InputKind
    input_path: Path | None = None
    structured_input: Mapping[str, Any] | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    capability_id: str
    producer_name: str
    producer_version: str
    candidates: tuple[CanonicalCandidate, ...]
    run_id: str | None = None
    source_name: str | None = None
    source_version: str | None = None
    source_checksum: str | None = None
    attribution: str | None = None
    licence: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    value_type: str
    required: bool = False
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    display_name: str
    version: str
    inputs: frozenset[InputKind]
    outputs: frozenset[str]
    parameters: tuple[ParameterDefinition, ...] = ()
    offline: bool = True


@runtime_checkable
class CapabilityEngine(Protocol):
    descriptor: CapabilityDescriptor

    def execute(self, request: CapabilityRequest) -> CapabilityResult: ...
    def release(self) -> None: ...


@runtime_checkable
class CapabilityRouter(Protocol):
    def discover(self) -> Sequence[CapabilityDescriptor]: ...
    def execute(self, request: CapabilityRequest) -> CapabilityResult: ...
    def deactivate(self, capability_id: str) -> None: ...
