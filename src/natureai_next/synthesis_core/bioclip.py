"""BioCLIP capability adapter for the stable SynthesisCore boundary."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from natureai_next.domain.enrichment import CanonicalCandidate, CanonicalShape
from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityRequest,
    CapabilityResult,
    InputKind,
    ParameterDefinition,
)


class BioCLIPClassifier(Protocol):
    identity: str
    last_prediction_rows: tuple[dict[str, Any], ...]

    def predict(self, image: Path, *, limit: int = 10) -> Sequence[object]: ...


class BioCLIPCapability:
    """Route the existing local BioCLIP classifier through CapabilityResult.

    The classifier remains responsible for model/runtime details.  This adapter
    owns only parameter validation and producer-neutral result normalization.
    """

    descriptor = CapabilityDescriptor(
        capability_id="aperture.bioclip",
        display_name="BioCLIP Tree of Life",
        version="4.0.0.dev1",
        inputs=frozenset({InputKind.PHOTO}),
        outputs=frozenset({CanonicalShape.TAXONOMY_CANDIDATE.value, CanonicalShape.LABEL.value}),
        parameters=(ParameterDefinition("top_k", "integer", default=10, minimum=1, maximum=50),),
        offline=True,
    )

    def __init__(self, classifier: BioCLIPClassifier) -> None:
        self._classifier = classifier

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        if request.input_kind is not InputKind.PHOTO:
            raise ValueError("BioCLIP accepts photo input only")
        if request.input_path is None:
            raise ValueError("BioCLIP requires an input_path")
        top_k = _integer_parameter(request.parameters, "top_k", default=10, minimum=1, maximum=50)
        predictions = tuple(self._classifier.predict(request.input_path, limit=top_k))
        upstream = self._classifier.last_prediction_rows
        candidates: list[CanonicalCandidate] = []
        for index, prediction in enumerate(predictions):
            row = upstream[index] if index < len(upstream) else {}
            label = str(
                getattr(prediction, "label", "") or row.get("scientific_name") or ""
            ).strip()
            if not label:
                continue
            confidence = _confidence(getattr(prediction, "raw_score", None))
            scientific_name = str(
                row.get("scientific_name") or row.get("species") or label.split(" (", 1)[0]
            ).strip()
            rank = (
                str(
                    row.get("rank")
                    or row.get("taxonomic_rank")
                    or getattr(prediction, "taxonomic_level", None)
                    or "species"
                )
                .strip()
                .casefold()
            )
            external_id = _external_id(row)
            value = {
                "label": label,
                "scientific_name": scientific_name,
                "rank": rank,
                "common_name": _optional_text(row.get("common_name") or row.get("common")),
            }
            candidates.append(
                CanonicalCandidate(
                    CanonicalShape.TAXONOMY_CANDIDATE,
                    {key: value for key, value in value.items() if value is not None},
                    confidence=confidence,
                    external_id=external_id,
                )
            )
        if not candidates:
            raise RuntimeError("BioCLIP returned no usable taxonomy candidates")
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name="BioCLIP TreeOfLife-10M",
            source_version=str(getattr(self._classifier, "identity", "unknown")),
            attribution="BioCLIP and TreeOfLife-10M contributors",
            licence="See installed BioCLIP bundle licence",
            diagnostics={"candidate_count": len(candidates), "top_k": top_k},
        )

    def release(self) -> None:
        release = getattr(self._classifier, "release", None)
        if callable(release):
            release()
        else:
            unload = getattr(self._classifier, "unload", None)
            if callable(unload):
                unload()


def _integer_parameter(
    parameters: object, name: str, *, default: int, minimum: int, maximum: int
) -> int:
    mapping = parameters if isinstance(parameters, dict) else dict(parameters)  # type: ignore[arg-type]
    raw = mapping.get(name, default)
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _confidence(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return max(0.0, min(1.0, number))


def _external_id(row: dict[str, Any]) -> str | None:
    for key in ("taxon_id", "taxon_key", "gbif_id", "id"):
        value = _optional_text(row.get(key))
        if value:
            return f"treeoflife:{value}"
    return None


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
