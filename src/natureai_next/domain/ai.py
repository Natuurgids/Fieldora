"""Provider-independent AI domain models and invariants."""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ExecutionDevice(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"


class Precision(StrEnum):
    FP32 = "fp32"
    FP16 = "fp16"


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ModelVariantManifest:
    identity: str
    runtime: str
    precision: Precision
    providers: tuple[str, ...]
    preprocessing_identity: str
    embedding_dimension: int
    input_size: int
    normalized_output: bool
    artifact_path: str


@dataclass(frozen=True, slots=True)
class ModelPackageManifest:
    schema_version: int
    package_id: str
    model_identity: str
    semantic_version: str
    model_family: str
    upstream_source: str
    license_name: str
    attribution_text: str
    minimum_application_version: str
    signing_key_id: str
    artifacts: tuple[ModelArtifact, ...]
    variants: tuple[ModelVariantManifest, ...]


@dataclass(frozen=True, slots=True)
class ActiveAIContext:
    model_variant_id: int
    model_identity: str
    model_version: str
    variant_identity: str
    precision: str
    preprocessing_identity: str
    input_size: int
    artifact_path: Path
    prompt_set_public_id: str
    execution_provider: str
    device: str


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.values or any(not math.isfinite(value) for value in self.values):
            raise ValueError("embedding must contain finite values")

    @property
    def dimension(self) -> int:
        return len(self.values)

    def normalized(self) -> EmbeddingVector:
        norm = math.sqrt(sum(value * value for value in self.values))
        if norm <= 0.0:
            raise ValueError("zero-length embedding cannot be normalized")
        return EmbeddingVector(tuple(value / norm for value in self.values))

    def to_blob(self) -> bytes:
        return struct.pack(f"<{self.dimension}f", *self.values)

    @classmethod
    def from_blob(cls, blob: bytes, dimension: int) -> EmbeddingVector:
        expected = dimension * 4
        if len(blob) != expected:
            raise ValueError(f"embedding blob has {len(blob)} bytes; expected {expected}")
        return cls(tuple(float(value) for value in struct.unpack(f"<{dimension}f", blob)))

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.to_blob()).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingProvenance:
    model_variant_public_id: str
    preprocessing_identity: str
    execution_provider: str
    precision: Precision
    application_version: str


@dataclass(frozen=True, slots=True)
class SimilarityMatch:
    asset_public_id: str
    score: float


@dataclass(frozen=True, slots=True)
class ProviderDiagnostics:
    provider: str
    available: bool
    torch_version: str | None
    cuda_runtime: str | None
    device_name: str | None
    compute_capability: str | None
    total_memory_bytes: int | None
    detail: str | None = None


class SuggestionReviewState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    label: str
    text: str
    taxon_public_id: str | None = None
    broad_group: str | None = None


@dataclass(frozen=True, slots=True)
class PromptSetManifest:
    schema_version: int
    identity: str
    semantic_version: str
    model_family: str
    minimum_application_version: str
    prompts: tuple[PromptDefinition, ...]


@dataclass(frozen=True, slots=True)
class SuggestionCandidate:
    taxon_public_id: str | None
    label: str
    raw_score: float
    calibrated_score: float | None
    rank: int
    confidence_band: ConfidenceBand
    taxonomic_level: str | None = None


@dataclass(frozen=True, slots=True)
class SuggestionProjection:
    public_id: str
    asset_public_id: str
    candidate_taxon_public_id: str | None
    candidate_label: str | None
    raw_score: float
    calibrated_score: float | None
    rank: int
    confidence_band: ConfidenceBand
    taxonomic_level: str | None
    review_state: SuggestionReviewState
    provenance_json: str
    region_of_interest_public_id: str | None = None
    assigned_to: str | None = None


@dataclass(frozen=True, slots=True)
class SuggestionPage:
    items: tuple[SuggestionProjection, ...]
    next_cursor: int | None


@dataclass(frozen=True, slots=True)
class PromptSetRecord:
    public_id: str
    identity: str
    semantic_version: str
    model_family: str
    checksum: str
    active: bool
    installed_at_us: int


@dataclass(frozen=True, slots=True)
class ReviewBatchResult:
    reviewed: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SuggestionDetail:
    suggestion: SuggestionProjection
    asset_title: str | None
    asset_caption: str | None
    taxon_scientific_name: str | None
    taxon_rank: str | None
    regional_occurrence_status: str | None
    geographic_context_json: str
    score_type: str
    calibration_identity: str | None
    prompt_set_identity: str | None
    prompt_set_version: str | None
    inference_run_public_id: str
    model_variant_public_id: str
    preprocessing_identity: str
    execution_provider: str
    precision: str | None
    created_at_us: int
    asset_primary_path: str | None = None
    asset_thumbnail_path: str | None = None
    asset_capture_time_utc_us: int | None = None
    asset_capture_local_text: str | None = None
    inference_image_path: str | None = None
    inference_image_width: int | None = None
    inference_image_height: int | None = None


@dataclass(frozen=True, slots=True)
class TaxonomyEmbeddingRefreshPlan:
    model_variant_id: int
    preprocessing_identity: str
    prompt_set_public_id: str | None
    model_family: str

    def __post_init__(self) -> None:
        if self.model_variant_id <= 0:
            raise ValueError("model_variant_id must be positive")
        if not self.preprocessing_identity.strip():
            raise ValueError("preprocessing_identity is required")
        if not self.model_family.strip():
            raise ValueError("model_family is required")


@dataclass(frozen=True, slots=True)
class TaxonomyTextEmbedding:
    public_id: str
    taxon_public_id: str | None
    broad_group: str | None
    label_kind: str
    source_text: str
    language_tag: str | None
    region_code: str | None
    vector: EmbeddingVector


@dataclass(frozen=True, slots=True)
class NearDuplicateMember:
    asset_public_id: str
    similarity: float
    position: int


@dataclass(frozen=True, slots=True)
class NearDuplicateGroup:
    public_id: str
    threshold: float
    members: tuple[NearDuplicateMember, ...]


@dataclass(frozen=True, slots=True)
class AIReviewSessionState:
    state_json: str
    modified_at_us: int


@dataclass(frozen=True, slots=True)
class TaxonomyTextLabel:
    taxon_public_id: str | None
    broad_group: str | None
    label_kind: str
    text: str
    language_tag: str | None = None
    region_code: str | None = None

    def __post_init__(self) -> None:
        if (self.taxon_public_id is None) == (self.broad_group is None):
            raise ValueError("exactly one taxonomy label owner is required")
        if self.label_kind not in {"scientific", "vernacular", "synonym", "broad_group"}:
            raise ValueError("unsupported taxonomy label kind")
        if not self.text.strip():
            raise ValueError("taxonomy label text is required")


class AnalysisStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AssetAnalysisRecord:
    public_id: str
    asset_public_id: str
    engine_id: str
    engine_family: str
    model_name: str | None
    model_version: str | None
    analysis_kind: str
    status: AnalysisStatus
    configuration_json: str
    configuration_hash: str
    result_summary_json: str
    source_sha256: str | None
    application_version: str
    started_at_us: int
    completed_at_us: int | None
    created_at_us: int


@dataclass(frozen=True, slots=True)
class AnalysisTaxonCandidateRecord:
    public_id: str
    analysis_public_id: str
    model_label: str
    rank: int
    raw_score: float
    calibrated_score: float | None
    confidence_band: ConfidenceBand
    local_taxon_public_id: str | None = None
    reference_taxon_public_id: str | None = None
    taxonomic_level: str | None = None
    provenance_json: str = "{}"
