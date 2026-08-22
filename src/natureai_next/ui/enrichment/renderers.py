"""Generic renderer selection by canonical shape rather than model identity."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from natureai_next.application.enrichment_projection import ProjectedEnrichment
from natureai_next.domain.enrichment import CanonicalShape, EnrichmentStatus


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    enrichment_id: str
    status: EnrichmentStatus


@dataclass(frozen=True, slots=True)
class RenderedEnrichment:
    enrichment_id: str
    component: str
    title: str
    fields: tuple[tuple[str, str], ...]
    provenance: tuple[tuple[str, str], ...]
    can_accept: bool
    can_reject: bool
    visualization: Mapping[str, Any] = None


Renderer = Callable[[ProjectedEnrichment], RenderedEnrichment]


class EnrichmentRendererRegistry:
    def __init__(self) -> None:
        self._renderers: dict[str, Renderer] = {}

    def register(self, shape: CanonicalShape | str, renderer: Renderer) -> None:
        key = shape.value if isinstance(shape, CanonicalShape) else str(shape)
        self._renderers[key] = renderer

    def render(self, item: ProjectedEnrichment) -> RenderedEnrichment:
        renderer = self._renderers.get(item.shape, _generic_renderer)
        return renderer(item)

    def review_command(self, item: ProjectedEnrichment, status: EnrichmentStatus) -> ReviewCommand:
        if item.status not in {
            EnrichmentStatus.GENERATED.value,
            EnrichmentStatus.PENDING_REVIEW.value,
            EnrichmentStatus.ACCEPTED.value,
            EnrichmentStatus.REJECTED.value,
        }:
            raise ValueError(f"enrichment in status {item.status!r} cannot be reviewed")
        if status not in {EnrichmentStatus.ACCEPTED, EnrichmentStatus.REJECTED}:
            raise ValueError("review command must accept or reject")
        return ReviewCommand(item.enrichment_id, status)


def default_renderer_registry() -> EnrichmentRendererRegistry:
    registry = EnrichmentRendererRegistry()
    registry.register(CanonicalShape.LABEL, _label_renderer)
    registry.register(CanonicalShape.TAXONOMY_CANDIDATE, _taxonomy_renderer)
    registry.register(CanonicalShape.BOUNDING_BOX, _spatial_renderer)
    registry.register(CanonicalShape.SEGMENTATION, _spatial_renderer)
    registry.register(CanonicalShape.TIME_SEGMENT, _timeline_renderer)
    registry.register(CanonicalShape.TIME_FREQUENCY_REGION, _timeline_renderer)
    registry.register(CanonicalShape.TRANSCRIPT_SEGMENT, _transcript_renderer)
    registry.register(CanonicalShape.DOCUMENT_REGION, _document_renderer)
    registry.register(CanonicalShape.MEASUREMENT, _measurement_renderer)
    registry.register(CanonicalShape.RELATIONSHIP, _relationship_renderer)
    registry.register(CanonicalShape.ARTIFACT_REFERENCE, _artifact_renderer)
    return registry


def _base(
    item: ProjectedEnrichment,
    component: str,
    title: str,
    fields: list[tuple[str, str]],
    *,
    visualization: Mapping[str, Any] | None = None,
) -> RenderedEnrichment:
    provenance = tuple(
        (key.replace("_", " ").title(), str(value))
        for key, value in item.provenance.items()
        if value not in (None, "")
    )
    pending = item.status in {
        EnrichmentStatus.GENERATED.value,
        EnrichmentStatus.PENDING_REVIEW.value,
    }
    return RenderedEnrichment(
        item.enrichment_id,
        component,
        title,
        tuple(fields),
        provenance,
        can_accept=pending,
        can_reject=pending,
        visualization=dict(visualization or {}),
    )


def _label_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    label = str(item.value.get("label") or item.summary or "Label")
    return _base(item, "label-list", label, [("Confidence", _confidence(item))])


def _taxonomy_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    title = str(
        item.value.get("scientific_name") or item.value.get("label") or "Taxonomy candidate"
    )
    fields = [("Rank", str(item.value.get("rank") or "unknown")), ("Confidence", _confidence(item))]
    external = item.value.get("external_id")
    if external:
        fields.append(("External ID", str(external)))
    return _base(item, "taxonomy-candidate-list", title, fields)


def _spatial_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    target = dict(item.target)
    visualization: dict[str, Any] = {"kind": "spatial"}
    if item.shape == CanonicalShape.BOUNDING_BOX.value:
        visualization["boxes"] = (_normalized_box(target),)
    else:
        points = target.get("points") or item.value.get("points") or ()
        visualization["polygons"] = (
            (tuple(_normalized_point(point) for point in points),) if points else ()
        )
    return _base(
        item,
        "spatial-overlay",
        item.summary or "Spatial result",
        _mapping_fields(target),
        visualization=visualization,
    )


def _timeline_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    fields = _mapping_fields(item.target)
    fields.append(("Confidence", _confidence(item)))
    start = _number(item.target.get("start_seconds") or item.target.get("start_s") or 0.0)
    end = _number(item.target.get("end_seconds") or item.target.get("end_s") or start)
    visualization = {
        "kind": "time-frequency"
        if item.shape == CanonicalShape.TIME_FREQUENCY_REGION.value
        else "timeline",
        "start_seconds": start,
        "end_seconds": max(start, end),
        "low_hz": _optional_number(item.target.get("low_hz")),
        "high_hz": _optional_number(item.target.get("high_hz")),
    }
    return _base(
        item,
        "timeline-event-list",
        item.summary or str(item.value.get("label") or "Timeline event"),
        fields,
        visualization=visualization,
    )


def _transcript_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    text = str(item.value.get("text") or item.summary or "Transcript")
    visualization = {
        "kind": "transcript",
        "text": text,
        "start_seconds": _optional_number(
            item.target.get("start_seconds") or item.target.get("start_s")
        ),
        "end_seconds": _optional_number(item.target.get("end_seconds") or item.target.get("end_s")),
        "speaker": item.value.get("speaker"),
    }
    return _base(
        item, "transcript-viewer", text, _mapping_fields(item.target), visualization=visualization
    )


def _document_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    visualization = {
        "kind": "document-region",
        "page": int(_number(item.target.get("page") or item.target.get("page_number") or 1)),
        "box": _normalized_box(item.target),
        "text": item.value.get("text"),
        "region_type": item.value.get("region_type") or item.value.get("type"),
    }
    return _base(
        item,
        "document-region-overlay",
        item.summary or "Document region",
        _mapping_fields(item.target),
        visualization=visualization,
    )


def _measurement_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    return _base(
        item, "measurement-table", item.summary or "Measurement", _mapping_fields(item.value)
    )


def _relationship_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    return _base(
        item, "relationship-viewer", item.summary or "Relationship", _mapping_fields(item.value)
    )


def _artifact_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    return _base(
        item, "artifact-reference", item.summary or "Artifact", _mapping_fields(item.value)
    )


def _generic_renderer(item: ProjectedEnrichment) -> RenderedEnrichment:
    return _base(
        item, "enrichment-summary", item.summary or item.shape, _mapping_fields(item.value)
    )


def _mapping_fields(mapping: dict[str, object]) -> list[tuple[str, str]]:
    return [(key.replace("_", " ").title(), str(value)) for key, value in mapping.items()]


def _confidence(item: ProjectedEnrichment) -> str:
    return "—" if item.confidence is None else f"{item.confidence:.1%}"


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    return _number(value)


def _unit(value: object) -> float:
    return min(1.0, max(0.0, _number(value)))


def _normalized_box(mapping: Mapping[str, object]) -> dict[str, float]:
    x = mapping.get("x", mapping.get("left", 0.0))
    y = mapping.get("y", mapping.get("top", 0.0))
    width = mapping.get("width")
    height = mapping.get("height")
    if width is None:
        width = _number(mapping.get("right")) - _number(x)
    if height is None:
        height = _number(mapping.get("bottom")) - _number(y)
    return {"x": _unit(x), "y": _unit(y), "width": _unit(width), "height": _unit(height)}


def _normalized_point(point: object) -> tuple[float, float]:
    if isinstance(point, Mapping):
        return (_unit(point.get("x")), _unit(point.get("y")))
    if isinstance(point, tuple | list) and len(point) >= 2:
        return (_unit(point[0]), _unit(point[1]))
    return (0.0, 0.0)
