"""Catalog-driven generic model execution into canonical Aperture enrichment."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from natureai_next.application.enrichment import (
    CanonicalEnrichment,
    CanonicalEnrichmentService,
    EnrichmentLabel,
    EnrichmentValue,
)


@dataclass(frozen=True, slots=True)
class GenericModelRunRequest:
    model_key: str
    subject_type: str
    subject_public_id: str
    inputs: object
    parameters: dict[str, object]


class CatalogEnrichmentRunner:
    def __init__(
        self,
        manager: object,
        enrichments: CanonicalEnrichmentService,
        id_factory: Callable[[], str],
    ) -> None:
        self._manager = manager
        self._enrichments = enrichments
        self._id_factory = id_factory

    def run(self, request: GenericModelRunRequest) -> CanonicalEnrichment:
        spec = self._manager.catalog.get(request.model_key)
        raw = self._manager.infer(request.model_key, request.inputs, request.parameters)
        if not isinstance(raw, dict):
            raw = {"result": raw}
        output = spec.output_contract
        fields = tuple(output.get("fields") or ())
        values: list[EnrichmentValue] = []
        labels: list[EnrichmentLabel] = []
        for field in fields:
            key = str(field["key"])
            if key not in raw:
                continue
            value_type = str(field.get("type") or "text")
            confidence = _confidence(raw, field)
            values.append(
                EnrichmentValue(
                    key=key, value=raw[key], value_type=value_type, confidence=confidence
                )
            )
            if bool(field.get("label", False)):
                labels.append(
                    EnrichmentLabel(
                        namespace=str(
                            field.get("namespace") or output.get("enrichment_type") or "model"
                        ),
                        key=str(raw[key]),
                        display_value=str(raw[key]),
                        confidence=confidence,
                        source=spec.key,
                    )
                )
        confidence = _overall_confidence(raw)
        item = CanonicalEnrichment(
            enrichment_id=self._id_factory(),
            subject_type=request.subject_type,
            subject_public_id=request.subject_public_id,
            enrichment_type=str(output.get("enrichment_type") or f"model.{spec.key}"),
            producer_id=spec.key,
            producer_version=spec.version,
            status="generated",
            confidence=confidence,
            summary=str(raw.get("summary") or raw.get("label") or spec.display_name),
            payload={"parameters": request.parameters, "result": raw},
            values=tuple(values),
            labels=tuple(labels),
        )
        self._enrichments.store(item)
        return item


def _overall_confidence(raw: dict[str, Any]) -> float | None:
    value = raw.get("confidence")
    return float(value) if isinstance(value, int | float) else None


def _confidence(raw: dict[str, Any], field: dict[str, Any]) -> float | None:
    confidence_key = field.get("confidence_key")
    value = raw.get(str(confidence_key)) if confidence_key else raw.get("confidence")
    return float(value) if isinstance(value, int | float) else None
