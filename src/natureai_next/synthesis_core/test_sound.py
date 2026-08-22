"""Small bundled offline sound capability used for lifecycle validation.

It intentionally performs no ML inference.  It accepts explicit time events from
structured input, making the complete sound path testable without shipping a
large model or native audio dependency.
"""

from __future__ import annotations

from natureai_next.domain.enrichment import CanonicalCandidate, CanonicalShape
from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityRequest,
    CapabilityResult,
    InputKind,
    ParameterDefinition,
)


class FixtureSoundEventCapability:
    descriptor = CapabilityDescriptor(
        capability_id="aperture.fixture.sound-events",
        display_name="Offline Sound Event Fixture",
        version="1.0.0",
        inputs=frozenset({InputKind.SOUND}),
        outputs=frozenset({CanonicalShape.TIME_SEGMENT.value, CanonicalShape.LABEL.value}),
        parameters=(ParameterDefinition("default_label", "string", default="sound event"),),
        offline=True,
    )

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        if request.input_kind is not InputKind.SOUND:
            raise ValueError("sound event fixture accepts sound input only")
        structured = dict(request.structured_input or {})
        events = structured.get("events", ())
        if not isinstance(events, list | tuple):
            raise ValueError("structured_input.events must be a list")
        default_label = str(request.parameters.get("default_label", "sound event")).strip()
        candidates: list[CanonicalCandidate] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("each sound event must be an object")
            start = _number(event.get("start_seconds"), "start_seconds")
            end = _number(event.get("end_seconds"), "end_seconds")
            if start < 0 or end <= start:
                raise ValueError("sound event requires 0 <= start_seconds < end_seconds")
            label = str(event.get("label") or default_label).strip()
            confidence = event.get("confidence")
            confidence_value = None if confidence is None else _number(confidence, "confidence")
            candidates.append(
                CanonicalCandidate(
                    CanonicalShape.TIME_SEGMENT,
                    {"label": label},
                    confidence=confidence_value,
                    target={"start_seconds": start, "end_seconds": end},
                )
            )
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name="Bundled deterministic sound fixture",
            source_version="1",
            attribution="Aperture",
            licence="CC0-1.0",
            diagnostics={"event_count": len(candidates)},
        )

    def release(self) -> None:
        return None


def _number(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if number != number:
        raise ValueError(f"{field} must be finite")
    return number
