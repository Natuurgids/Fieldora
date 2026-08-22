"""Producer-neutral presentation and policy helpers for enrichment source lifecycle UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRemovalOptions,
    SourceState,
)


class SourceStateTone(StrEnum):
    READY = "ready"
    MUTED = "muted"
    WARNING = "warning"
    ERROR = "error"
    UPDATE = "update"


_STATE_PRESENTATION: dict[SourceState, tuple[str, SourceStateTone, str]] = {
    SourceState.INSTALLED: ("Installed", SourceStateTone.READY, "Available for local execution."),
    SourceState.OFFLINE: (
        "Offline",
        SourceStateTone.MUTED,
        "Installed for offline use; no network access is required.",
    ),
    SourceState.INACTIVE: (
        "Inactive",
        SourceStateTone.MUTED,
        "Installed but disabled until activated.",
    ),
    SourceState.REMOVED: (
        "Removed",
        SourceStateTone.MUTED,
        "Managed runtime files were removed; preserved accepted enrichment remains readable.",
    ),
    SourceState.MISSING: (
        "Missing",
        SourceStateTone.ERROR,
        "The registry entry remains, but expected files are unavailable.",
    ),
    SourceState.SUPERSEDED: (
        "Superseded",
        SourceStateTone.WARNING,
        "A replacement source version is preferred; existing provenance remains valid.",
    ),
    SourceState.REQUIRES_DOWNLOAD: (
        "Download required",
        SourceStateTone.WARNING,
        "The capability is known but its runtime files are not installed.",
    ),
    SourceState.UPDATE_AVAILABLE: (
        "Update available",
        SourceStateTone.UPDATE,
        "A newer source version is available for installation.",
    ),
}


@dataclass(frozen=True, slots=True)
class SourceStatePresentation:
    label: str
    tone: SourceStateTone
    explanation: str
    can_activate: bool
    can_deactivate: bool
    can_remove_files: bool


@dataclass(frozen=True, slots=True)
class SourceRemovalPreview:
    pending_to_delete: int
    rejected_to_delete: int
    accepted_to_delete: int
    accepted_to_preserve: int
    reproducibility_warning: bool

    @property
    def total_to_delete(self) -> int:
        return self.pending_to_delete + self.rejected_to_delete + self.accepted_to_delete

    def summary(self) -> str:
        preserved = f"{self.accepted_to_preserve} accepted record(s) preserved"
        deleted = f"{self.total_to_delete} canonical record(s) deleted"
        warning = (
            " Runtime removal may prevent future reproduction."
            if self.reproducibility_warning
            else ""
        )
        return f"{deleted}; {preserved}.{warning}"


def present_source_state(record: SourceRecord) -> SourceStatePresentation:
    label, tone, explanation = _STATE_PRESENTATION[record.state]
    return SourceStatePresentation(
        label=label,
        tone=tone,
        explanation=explanation,
        can_activate=record.state
        in {
            SourceState.INACTIVE,
            SourceState.OFFLINE,
            SourceState.UPDATE_AVAILABLE,
            SourceState.SUPERSEDED,
        },
        can_deactivate=record.state
        in {
            SourceState.INSTALLED,
            SourceState.OFFLINE,
            SourceState.UPDATE_AVAILABLE,
        },
        can_remove_files=record.state not in {SourceState.REMOVED, SourceState.REQUIRES_DOWNLOAD},
    )


def preview_source_removal(
    counts: dict[str, int],
    options: SourceRemovalOptions,
) -> SourceRemovalPreview:
    pending = int(counts.get("generated", 0)) + int(counts.get("pending_review", 0))
    rejected = int(counts.get("rejected", 0))
    accepted = int(counts.get("accepted", 0))
    return SourceRemovalPreview(
        pending_to_delete=pending if options.delete_pending_results else 0,
        rejected_to_delete=rejected if options.delete_rejected_results else 0,
        accepted_to_delete=accepted if options.delete_accepted_enrichment else 0,
        accepted_to_preserve=0 if options.delete_accepted_enrichment else accepted,
        reproducibility_warning=bool(
            options.remove_runtime_files or options.remove_indexes_and_caches
        ),
    )
