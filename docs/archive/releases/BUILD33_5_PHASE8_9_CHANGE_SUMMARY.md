# Build 33.5 — Phases 8 and 9

## Phase 8: explicit workflow graphs

- Added a reusable, accessible `WorkflowGraphWidget` built from ordinary Qt controls.
- Model catalog workflows now render as explicit directed graphs with runtime state.
- Knowledge Sources uses the same graph vocabulary instead of a one-off text chain.
- Graph nodes expose descriptions and state to keyboard and accessibility APIs.

## Phase 9: unified enrichment pipeline

- Added one producer-neutral pipeline across Photos, Videos, Sounds and Documents:
  Media evidence → AI analysis → Candidate → optional Knowledge Sources → Knowledge Base review → Accepted observation.
- The canonical enrichment panel updates pipeline state from pending, accepted and rejected counts.
- The presentation preserves the authority boundary: optional sources corroborate; only user review creates accepted observations.
- No engine-specific schema or direct cross-domain repository access was introduced.

## Compatibility

Existing model installation, activation, enrichment review, playback synchronization, provenance, overlays, reporting and library behavior are retained.
