"""AI suggestion generation, review, semantic search, and duplicate grouping."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.domain.ai import (
    ConfidenceBand,
    EmbeddingVector,
    PromptSetRecord,
    ReviewBatchResult,
    SimilarityMatch,
    SuggestionCandidate,
    SuggestionDetail,
    SuggestionPage,
    TaxonomyTextEmbedding,
    TaxonomyTextLabel,
)
from natureai_next.ports.ai_review import (
    PromptSetLoader,
    PromptSetStore,
    SuggestionStore,
    TaxonomyEmbeddingStore,
    TaxonomyLabelSource,
)


@dataclass(frozen=True, slots=True)
class ReviewFilter:
    state: str = "pending"
    confidence: tuple[str, ...] = ()
    taxonomic_level: str | None = None
    assigned_to: str | None = None


@dataclass(frozen=True, slots=True)
class AIReviewOverview:
    active_model_identity: str | None
    active_model_version: str | None
    active_variant_identity: str | None
    active_prompt_set: str | None
    suggestion_counts: tuple[tuple[str, int], ...]
    latest_run_outcome: str | None
    latest_run_completed: int
    latest_run_failed: int

    def count(self, state: str) -> int:
        return dict(self.suggestion_counts).get(state, 0)


class CosineCandidateRanker:
    def __init__(self, *, high: float = 0.30, medium: float = 0.20, low: float = 0.10) -> None:
        if not 0 <= low <= medium <= high <= 1:
            raise ValueError("invalid confidence thresholds")
        self._high = high
        self._medium = medium
        self._low = low

    def rank(
        self,
        image: EmbeddingVector,
        candidates: Sequence[tuple[str, str, EmbeddingVector]],
        *,
        region_code: str | None,
        limit: int,
    ) -> tuple[SuggestionCandidate, ...]:
        del region_code
        query = image.normalized()
        scored: list[tuple[float, str, str]] = []
        for taxon_id, label, vector in candidates:
            normalized = vector.normalized()
            if normalized.dimension != query.dimension:
                continue
            score = math.fsum(
                left * right for left, right in zip(query.values, normalized.values, strict=True)
            )
            scored.append((score, taxon_id, label))
        scored.sort(key=lambda item: (-item[0], item[2].casefold(), item[1]))
        result: list[SuggestionCandidate] = []
        for rank, (score, taxon_id, label) in enumerate(scored[: max(1, min(limit, 100))], start=1):
            if score >= self._high:
                band = ConfidenceBand.HIGH
            elif score >= self._medium:
                band = ConfidenceBand.MEDIUM
            elif score >= self._low:
                band = ConfidenceBand.LOW
            else:
                band = ConfidenceBand.UNKNOWN
            result.append(
                SuggestionCandidate(
                    taxon_public_id=taxon_id,
                    label=label,
                    raw_score=score,
                    calibrated_score=score,
                    rank=rank,
                    confidence_band=band,
                )
            )
        return tuple(result)


class RegionalCandidateRanker:
    """Applies bounded, explicit occurrence adjustments after cosine scoring."""

    def __init__(
        self,
        base: CosineCandidateRanker,
        *,
        native_boost: float = 0.04,
        present_boost: float = 0.02,
        absent_penalty: float = 0.08,
    ) -> None:
        if min(native_boost, present_boost, absent_penalty) < 0:
            raise ValueError("regional ranking adjustments must be non-negative")
        self._base = base
        self._adjustments = {
            "native": native_boost,
            "present": present_boost,
            "established": present_boost,
            "introduced": present_boost / 2,
            "absent": -absent_penalty,
            "not_recorded": -absent_penalty / 2,
        }

    def rank(
        self,
        image: EmbeddingVector,
        candidates: Sequence[tuple[str, str, EmbeddingVector]],
        *,
        region_code: str | None,
        limit: int,
        occurrence_by_taxon: dict[str, str] | None = None,
    ) -> tuple[SuggestionCandidate, ...]:
        base = self._base.rank(image, candidates, region_code=region_code, limit=max(limit, 100))
        occurrence_by_taxon = occurrence_by_taxon or {}
        adjusted: list[SuggestionCandidate] = []
        for candidate in base:
            status = occurrence_by_taxon.get(candidate.taxon_public_id or "", "")
            score = max(-1.0, min(1.0, candidate.raw_score + self._adjustments.get(status, 0.0)))
            adjusted.append(
                SuggestionCandidate(
                    taxon_public_id=candidate.taxon_public_id,
                    label=candidate.label,
                    raw_score=candidate.raw_score,
                    calibrated_score=score,
                    rank=0,
                    confidence_band=candidate.confidence_band,
                    taxonomic_level=candidate.taxonomic_level,
                )
            )
        adjusted.sort(
            key=lambda candidate: (
                -(candidate.calibrated_score if candidate.calibrated_score is not None else -1.0),
                candidate.label.casefold(),
                candidate.taxon_public_id or "",
            )
        )
        return tuple(
            SuggestionCandidate(
                taxon_public_id=item.taxon_public_id,
                label=item.label,
                raw_score=item.raw_score,
                calibrated_score=item.calibrated_score,
                rank=rank,
                confidence_band=item.confidence_band,
                taxonomic_level=item.taxonomic_level,
            )
            for rank, item in enumerate(adjusted[: max(1, min(limit, 100))], start=1)
        )


class PromptSetService:
    def __init__(
        self,
        store: PromptSetStore,
        *,
        loader: PromptSetLoader,
        checksum: Callable[[object], str],
        validator: Callable[..., None],
        application_version: str = __version__,
    ) -> None:
        self._store = store
        self._loader = loader
        self._checksum = checksum
        self._validator = validator
        self._application_version = application_version

    def install(
        self,
        path: Path,
        *,
        public_id: str,
        now_us: int,
        activate: bool = False,
        model_family: str | None = None,
    ) -> PromptSetRecord:
        manifest = self._loader(path)
        self._validator(
            manifest,
            application_version=self._application_version,
            model_family=model_family,
        )
        return self._store.install(
            manifest,
            checksum=self._checksum(manifest),
            public_id=public_id,
            now_us=now_us,
            activate=activate,
        )

    def activate(self, public_id: str, *, now_us: int) -> PromptSetRecord:
        return self._store.activate(public_id, now_us=now_us)

    def list(self, identity: str | None = None) -> tuple[PromptSetRecord, ...]:
        return self._store.list(identity)


class SuggestionService:
    def __init__(self, store: SuggestionStore) -> None:
        self._store = store

    def create(self, **kwargs: object) -> tuple[str, ...]:
        return self._store.create_suggestions(**kwargs)

    def page(
        self,
        *,
        filter: ReviewFilter,
        cursor: int | None = None,
        page_size: int = 100,
    ) -> SuggestionPage:
        return self._store.page(
            state=filter.state,
            confidence=filter.confidence,
            taxonomic_level=filter.taxonomic_level,
            assigned_to=filter.assigned_to,
            cursor=cursor,
            page_size=page_size,
        )

    def page_for_asset(
        self,
        asset_public_id: str,
        *,
        filter: ReviewFilter,
        cursor: int | None = None,
        page_size: int = 100,
    ) -> SuggestionPage:
        return self._store.page_for_asset(
            asset_public_id,
            state=filter.state,
            confidence=filter.confidence,
            taxonomic_level=filter.taxonomic_level,
            assigned_to=filter.assigned_to,
            cursor=cursor,
            page_size=page_size,
        )

    def detail(self, public_id: str, *, region_code: str | None = None) -> SuggestionDetail:
        return self._store.detail(public_id, region_code=region_code)

    def reject_other_suggestions(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult:
        return self._store.reject_other_suggestions(
            suggestion_public_id,
            action_id_factory=action_id_factory,
            now_us=now_us,
            reason=reason,
        )

    def accept_and_reject_others(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult:
        return self._store.accept_and_reject_others(
            suggestion_public_id,
            action_id_factory=action_id_factory,
            now_us=now_us,
        )

    def accept_all_pending_for_asset(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult:
        return self._store.accept_all_pending_for_asset(
            suggestion_public_id,
            action_id_factory=action_id_factory,
            now_us=now_us,
        )

    def reject_all_pending_for_asset(
        self,
        asset_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult:
        pending_ids: list[str] = []
        cursor: int | None = None
        while True:
            page = self.page_for_asset(
                asset_public_id,
                filter=ReviewFilter(state="pending"),
                cursor=cursor,
                page_size=500,
            )
            pending_ids.extend(item.public_id for item in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        if not pending_ids:
            return ReviewBatchResult(reviewed=(), failed=())
        return self.batch_review(
            pending_ids,
            action="reject",
            action_id_factory=action_id_factory,
            now_us=now_us,
            reason=reason,
        )

    def overview(self) -> AIReviewOverview:
        value = self._store.overview()
        if not isinstance(value, AIReviewOverview):
            raise TypeError("suggestion store returned an invalid AI review overview")
        return value

    def accept(self, suggestion_public_id: str, *, action_public_id: str, now_us: int) -> None:
        self._store.review(
            suggestion_public_id=suggestion_public_id,
            action="accept",
            action_public_id=action_public_id,
            now_us=now_us,
        )

    def reject(
        self,
        suggestion_public_id: str,
        *,
        action_public_id: str,
        now_us: int,
        reason: str | None = None,
    ) -> None:
        self._store.review(
            suggestion_public_id=suggestion_public_id,
            action="reject",
            action_public_id=action_public_id,
            now_us=now_us,
            reason=reason,
        )

    def defer(
        self,
        suggestion_public_id: str,
        *,
        action_public_id: str,
        now_us: int,
        reason: str | None = None,
    ) -> None:
        self._store.review(
            suggestion_public_id=suggestion_public_id,
            action="defer",
            action_public_id=action_public_id,
            now_us=now_us,
            reason=reason,
        )

    def assign(
        self,
        suggestion_public_id: str,
        *,
        assigned_to: str | None,
        assigned_by: str,
        now_us: int,
        note: str | None = None,
    ) -> None:
        self._store.assign_review(
            suggestion_public_id=suggestion_public_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            now_us=now_us,
            note=note,
        )

    def supersede(
        self,
        old_suggestion_public_id: str,
        new_suggestion_public_id: str,
        *,
        action_public_id: str,
        now_us: int,
        reason: str | None = None,
    ) -> None:
        self._store.supersede(
            old_suggestion_public_id,
            new_suggestion_public_id,
            action_public_id=action_public_id,
            now_us=now_us,
            reason=reason,
        )

    def reverse_acceptance(
        self, suggestion_public_id: str, *, action_public_id: str, now_us: int
    ) -> None:
        self._store.reverse_acceptance(
            suggestion_public_id=suggestion_public_id,
            action_public_id=action_public_id,
            now_us=now_us,
        )

    def batch_review(
        self,
        suggestion_public_ids: Sequence[str],
        *,
        action: str,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult:
        return self._store.batch_review(
            suggestion_public_ids,
            action=action,
            action_id_factory=action_id_factory,
            now_us=now_us,
            reason=reason,
        )


class SemanticSearchService:
    """Embeds local text and uses an active index with exact fallback."""

    def __init__(
        self,
        *,
        embed_text: Callable[[Sequence[str]], tuple[EmbeddingVector, ...]],
        index_search: Callable[..., tuple[SimilarityMatch, ...]],
    ) -> None:
        self._embed_text = embed_text
        self._index_search = index_search

    def search(
        self,
        text: str,
        *,
        index_id: int,
        index_directory: Path,
        model_variant_id: int,
        preprocessing_identity: str,
        limit: int = 50,
    ) -> tuple[SimilarityMatch, ...]:
        query_text = text.strip()
        if not query_text:
            raise ValueError("semantic search text is required")
        vectors = self._embed_text((query_text,))
        if len(vectors) != 1:
            raise RuntimeError("text encoder returned an unexpected number of vectors")
        return self._index_search(
            index_id=index_id,
            directory=index_directory,
            model_variant_id=model_variant_id,
            preprocessing_identity=preprocessing_identity,
            query=vectors[0],
            limit=limit,
        )


def near_duplicate_groups(
    vectors: dict[str, EmbeddingVector], *, threshold: float = 0.985
) -> tuple[tuple[str, ...], ...]:
    if not -1 <= threshold <= 1:
        raise ValueError("threshold out of range")
    keys = sorted(vectors)
    parent = {key: key for key in keys}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    normalized = {key: vector.normalized() for key, vector in vectors.items()}
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            left_vector = normalized[left]
            right_vector = normalized[right]
            if left_vector.dimension != right_vector.dimension:
                continue
            score = math.fsum(
                x * y for x, y in zip(left_vector.values, right_vector.values, strict=True)
            )
            if score >= threshold:
                union(left, right)
    groups: dict[str, list[str]] = {}
    for key in keys:
        groups.setdefault(find(key), []).append(key)
    return tuple(tuple(values) for _, values in sorted(groups.items()) if len(values) > 1)


@dataclass(frozen=True, slots=True)
class HierarchicalGenerationResult:
    broad_group: SuggestionCandidate | None
    candidates: tuple[SuggestionCandidate, ...]


class HierarchicalSuggestionGenerator:
    """Two-stage local classification: broad group, then bounded taxonomy candidates."""

    def __init__(
        self,
        *,
        ranker: CosineCandidateRanker,
        broad_group_candidates: Callable[[], Sequence[tuple[str, str, EmbeddingVector]]],
        taxon_candidates: Callable[[str, str | None], Sequence[tuple[str, str, EmbeddingVector]]],
        occurrence_resolver: Callable[[Sequence[str], str], dict[str, str]] | None = None,
        regional_ranker: RegionalCandidateRanker | None = None,
    ) -> None:
        self._ranker = ranker
        self._broad_group_candidates = broad_group_candidates
        self._taxon_candidates = taxon_candidates
        self._occurrence_resolver = occurrence_resolver
        self._regional_ranker = regional_ranker

    def generate(
        self,
        image: EmbeddingVector,
        *,
        region_code: str | None,
        limit: int = 10,
    ) -> HierarchicalGenerationResult:
        groups = self._ranker.rank(
            image,
            self._broad_group_candidates(),
            region_code=region_code,
            limit=1,
        )
        if not groups or groups[0].confidence_band is ConfidenceBand.UNKNOWN:
            return HierarchicalGenerationResult(groups[0] if groups else None, ())
        group_identity = groups[0].taxon_public_id or groups[0].label
        taxa = tuple(self._taxon_candidates(group_identity, region_code))
        if self._regional_ranker is not None and region_code is not None:
            occurrence = (
                self._occurrence_resolver(tuple(item[0] for item in taxa), region_code)
                if self._occurrence_resolver is not None
                else {}
            )
            candidates = self._regional_ranker.rank(
                image,
                taxa,
                region_code=region_code,
                limit=limit,
                occurrence_by_taxon=occurrence,
            )
        else:
            candidates = self._ranker.rank(image, taxa, region_code=region_code, limit=limit)
        return HierarchicalGenerationResult(groups[0], candidates)


class ReviewSessionService:
    def __init__(self, store: object) -> None:
        self._store = store

    def load(self) -> dict[str, object]:
        state = self._store.load()
        if state is None:
            return {}
        import json

        value = json.loads(state.state_json)
        if not isinstance(value, dict):
            raise ValueError("AI review session state must be a JSON object")
        return value

    def save(
        self,
        state: dict[str, object],
        *,
        public_id: str,
        now_us: int,
    ) -> None:
        import json

        self._store.save(
            json.dumps(state, sort_keys=True, separators=(",", ":")),
            public_id=public_id,
            now_us=now_us,
        )


@dataclass(frozen=True, slots=True)
class TaxonomyEmbeddingBuildResult:
    labels_seen: int
    embeddings_written: int
    batches: int


class TaxonomyTextEmbeddingService:
    """Builds one authoritative taxonomy-text embedding generation."""

    def __init__(
        self,
        *,
        labels: TaxonomyLabelSource,
        store: TaxonomyEmbeddingStore,
        embed_text: Callable[[Sequence[str]], tuple[EmbeddingVector, ...]],
        public_id_factory: Callable[[TaxonomyTextLabel], str],
    ) -> None:
        self._labels = labels
        self._store = store
        self._embed_text = embed_text
        self._public_id_factory = public_id_factory

    def rebuild(
        self,
        *,
        model_variant_id: int,
        preprocessing_identity: str,
        prompt_set_public_id: str | None,
        now_us: int,
        language_tags: Sequence[str] = (),
        region_codes: Sequence[str] = (),
        include_synonyms: bool = True,
        batch_size: int = 128,
        cancellation_check: Callable[[], None] = lambda: None,
        progress: Callable[[int, int], None] = lambda _current, _total: None,
    ) -> TaxonomyEmbeddingBuildResult:
        if model_variant_id <= 0:
            raise ValueError("model_variant_id must be positive")
        if not preprocessing_identity.strip():
            raise ValueError("preprocessing identity is required")
        if batch_size < 1 or batch_size > 2048:
            raise ValueError("batch size must be between 1 and 2048")
        release_ids = self._labels.active_release_ids()
        labels = self._labels.active_labels(
            language_tags=language_tags,
            region_codes=region_codes,
            include_synonyms=include_synonyms,
        )
        generation_payload = {
            "taxonomy_source_public_ids": release_ids,
            "model_variant_id": model_variant_id,
            "preprocessing_identity": preprocessing_identity,
            "prompt_set_public_id": prompt_set_public_id,
            "language_tags": tuple(language_tags),
            "region_codes": tuple(code.upper() for code in region_codes),
            "include_synonyms": include_synonyms,
        }
        generation_identity = hashlib.sha256(
            json.dumps(generation_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        generated: list[TaxonomyTextEmbedding] = []
        batches = 0
        for offset in range(0, len(labels), batch_size):
            cancellation_check()
            batch = labels[offset : offset + batch_size]
            vectors = self._embed_text(tuple(item.text for item in batch))
            if len(vectors) != len(batch):
                raise RuntimeError("text encoder returned an unexpected vector count")
            for label, vector in zip(batch, vectors, strict=True):
                generated.append(
                    TaxonomyTextEmbedding(
                        public_id=self._public_id_factory(label),
                        taxon_public_id=label.taxon_public_id,
                        broad_group=label.broad_group,
                        label_kind=label.label_kind,
                        source_text=label.text,
                        language_tag=label.language_tag,
                        region_code=label.region_code,
                        vector=vector.normalized(),
                    )
                )
            batches += 1
            progress(min(offset + len(batch), len(labels)), len(labels))
        written = self._store.replace_generation(
            model_variant_id=model_variant_id,
            preprocessing_identity=preprocessing_identity,
            prompt_set_public_id=prompt_set_public_id,
            embeddings=tuple(generated),
            now_us=now_us,
            generation_identity=generation_identity,
            taxonomy_source_public_ids=release_ids,
        )
        return TaxonomyEmbeddingBuildResult(len(labels), written, batches)
