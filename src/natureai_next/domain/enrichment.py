"""Producer-neutral Aperture enrichment domain contracts.

The observer-facing Aperture application owns these records.  Runtime engines only
produce :class:`CapabilityResult` values which are translated into these shapes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SubjectType(StrEnum):
    OBSERVATION = "observation"
    PHOTO = "photo"
    SOUND = "sound"
    VIDEO = "video"
    DOCUMENT = "document"


class EnrichmentStatus(StrEnum):
    GENERATED = "generated"
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class CanonicalShape(StrEnum):
    LABEL = "label"
    TAXONOMY_CANDIDATE = "taxonomy_candidate"
    BOUNDING_BOX = "bounding_box"
    SEGMENTATION = "segmentation"
    TIME_SEGMENT = "time_segment"
    TIME_FREQUENCY_REGION = "time_frequency_region"
    TRANSCRIPT_SEGMENT = "transcript_segment"
    DOCUMENT_REGION = "document_region"
    MEASUREMENT = "measurement"
    RELATIONSHIP = "relationship"
    ARTIFACT_REFERENCE = "artifact_reference"


@dataclass(frozen=True, slots=True)
class SubjectRef:
    subject_type: SubjectType
    public_id: str

    def __post_init__(self) -> None:
        if not self.public_id.strip():
            raise ValueError("subject public_id must not be blank")


@dataclass(frozen=True, slots=True)
class CanonicalCandidate:
    shape: CanonicalShape
    value: Mapping[str, Any]
    confidence: float | None = None
    target: Mapping[str, Any] = field(default_factory=dict)
    external_id: str | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("candidate confidence must be between 0 and 1")
        if not self.value:
            raise ValueError("candidate value must not be empty")


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    producer_name: str
    producer_version: str
    source_name: str | None = None
    source_version: str | None = None
    checksum: str | None = None
    attribution: str | None = None
    licence: str | None = None
    created_at_us: int | None = None


@dataclass(frozen=True, slots=True)
class CanonicalRecord:
    enrichment_id: str
    subject: SubjectRef
    candidate: CanonicalCandidate
    status: EnrichmentStatus
    source_id: str
    snapshot: SourceSnapshot
    created_at_us: int
    updated_at_us: int
    reviewed_at_us: int | None = None
    reviewer: str | None = None
