# Collapsible Lower Workspace Panel — UI Requirement

**Requested:** 2026-07-24  
**Scope:** Photo Library and other subject workspaces that use the same lower enrichment/review composition  
**Change type:** Implemented presentation-only, non-breaking interface enhancement
**Implementation status:** Implemented 2026-07-24 for Photos, Sounds, Videos, and Documents

## Objective

Allow the user to enlarge the primary photograph or media-results area by folding the lower review, visualization, enrichment, and provenance area into a single compact line.

## Required behaviour

- Provide an obvious expand/collapse control on the lower workspace area.
- In the collapsed state, the lower area occupies approximately one standard header/status line.
- The compact line should identify the area and may retain concise state counts, such as Pending, Accepted, and Rejected.
- Expanding restores the complete current lower workspace, including visualization, enrichment, provenance, Accept, Reject, Refresh, and other existing controls.
- Collapsing is a layout action only. It must not clear selection, cancel work, discard results, reset filters, change review status, or modify enrichment records.
- The photograph/media grid and preview area receives the released vertical space immediately.
- The control must work without blocking background import, enrichment, thumbnail generation, review, or other current operations.
- The expanded and collapsed states should be retained for the active workspace, and preferably persisted with the normal per-library window layout.
- Existing keyboard navigation, selection, scrolling, resizing, and inspector behaviour must remain unchanged.

## Functional preservation requirement

All functions that currently work must continue to work before, during, and after collapse or expansion. The implementation must reuse the existing workspace widgets rather than recreate or detach their data state merely to achieve the visual fold.

## Applicable screens

The implemented scope covers Photos, Sounds, Videos, and Documents. Observations and other workspaces are not changed by this implementation.

## Acceptance criteria

1. A user can reduce the lower section to one compact line with one action.
2. The photo/media area visibly grows to use the released space.
3. A second action restores the complete lower section.
4. Current selection and scroll position remain intact.
5. Pending, accepted, rejected, visualization, enrichment, and provenance state remain intact.
6. Import, enrichment, model execution, review, refresh, viewer, trash, and delete actions retain their existing behaviour.
7. No database, model, import, enrichment, export, or business-logic change is introduced by this UI enhancement.

## Implementation notes

- The existing canonical enrichment widget remains instantiated while collapsed; only its detail body is hidden.
- A compact summary line remains visible with Pending, Accepted, and Rejected counts and an **Expand details** control.
- Each of the four workspaces stores its collapsed state independently through normal Qt settings.
- No import, enrichment, model, review, viewer, database, export, or media-processing code path was changed.
