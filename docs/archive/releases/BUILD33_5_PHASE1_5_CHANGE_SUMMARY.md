# Build 33.5 — Media Workspace Refactor (Phases 1–5)

This release integrates the approved Build 33.5 workspace changes with the already completed Phase 6 Models experience and Phase 7 Knowledge Sources separation.

## Phase 1 — Workspace framework

- Added a reusable `MediaWorkspaceHost` that preserves the command/search surface, center workspace, permanent inspector, and bottom action bar.
- Added typed `MediaWorkspaceDescriptor` and `WorkspaceAction` contracts so media-specific presentation and commands are declared rather than scattered through layout code.
- Existing database queries, media selection, playback, overlays, enrichment execution, review, and provenance controllers remain unchanged.

## Phase 2 — Collapsible layout engine

- Added the standard `CollapsibleSection` widget.
- Collapse removes content height and spacing immediately and persists state through Qt settings.
- Structured Filters and media-specific Inspector sections use the same component.

## Phase 3 — Dedicated media workspaces

- Sounds: waveform overview, spectrogram, playback timeline and transport controls.
- Videos: video player, canonical overlay, timeline controls, frame/event strip.
- Documents: page rail, native document/PDF viewer, OCR overlay surface, and extracted-text pane.
- Photos retain the established photo workspace while the shared framework is introduced without changing photo-library behavior.

## Phase 4 — Adaptive inspector

- Inspector remains permanently docked.
- Sounds expose Recording metadata, Perch, BirdNET, Reference recordings, and Knowledge review sections.
- Videos expose Technical metadata, Timeline, YOLO, BioCLIP, and Whisper sections.
- Documents expose Document metadata, OCR confidence, Detected taxa, Locations, Dates, and People sections.
- Installed capability results continue to flow through the canonical enrichment panel.

## Phase 5 — Adaptive bottom toolbar

- Sounds: Play/Pause, Normalize, Run Enrichment.
- Videos: Play/Pause, Extract Audio, Detect Frames, Run Enrichment.
- Documents: OCR, Export Text, Run Enrichment.
- Actions requiring a selected media item remain disabled until a valid selection exists.

## Compatibility

The release does not change the Aperture Library schema or media-query contracts. Non-destructive actions continue to route through installed capabilities; originals are not modified.
