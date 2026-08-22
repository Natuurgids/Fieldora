# Aperture 4.0.0.dev1+build26.repair22

- Offline map asset bounds aligned with the rendered five-by-five tile window.
- Added database-backed viewport regression tests.

# Aperture 4.0.0.dev1+build26.repair21

## Repair 21

- Corrected the import planner ZIP-container guard.
- Verified recognized ZIP-based document formats pass planning.
- Preserved rejection of unknown ZIP archives.

# Aperture 4.0.0.dev1+build26.repair20

## Repair 20 — Offline map image locations

- Offline maps now preserve and display each image location role independently.
- Images with both capture and subject coordinates appear at both positions.
- Capture and subject markers use distinct styling and descriptive tooltips.
- Signed coordinates are shown with North, South, East, and West hemisphere labels.
- Existing observation, site, temporal-track, and offline basemap behavior is unchanged.

## Repair 18 — trash scroll retention and continuous paging — 2026-07-25

- Removed the post-trash full gallery refresh and model reset.
- Trash and permanent-delete completion now remove only affected model rows with `beginRemoveRows()`/`endRemoveRows()`.
- Preserved the active paging cursor and existing `QListView` instance after removal.
- Added guarded near-bottom paging from the vertical scrollbar.
- Added an event-loop follow-up that fetches another page when removal leaves the viewport underfilled or already at the end.
- Removed thumbnail queue/cache state only for affected asset IDs.

## Repair 17 — gallery virtualization and Perch dependency repair — 2026-07-25

- Replaced the Photos `QListWidget` grid with `QListView`, `QAbstractListModel`, and `QStyledItemDelegate`.
- Added fixed-size batched layout, viewport-aware thumbnail scheduling, and queued/in-flight/completed job deduplication.
- Added `kagglehub` to the Perch 2 dependency catalog.
- Made Perch health checking and enrichment share the same `Perch2()` initialization path with actionable dependency errors.
- Preserved the collapsible enrichment panel and existing library workflows.

# Current field-validation status — 2026-07-24

- **Imports:** Functioning for all tested import types.
- **Enrichment:** Functioning and taking place on imported records.
- **Export:** Not functioning. Latest run failed at 2 / 4 with `'str' object has no attribute 'value'`.
- **Video import:** Functioning.
- **Video model:** Not yet functioning correctly.
- **Other tested models:** Functioning.

This status supersedes broader implementation statements where they imply that export or video-model processing has passed field validation. See `FIELD_VALIDATION_STATUS.md`.

## Build 18 — Category-aware retention and audit

Completed per-category slimming previews and reports, preservation of durable OCR/geographic assertions, reproducibility warnings, and durable retention audit records.

## Build 17 — Generic capability execution

- Compatible capabilities are discovered by canonical input kind.
- Parameters are rendered and validated from manifests rather than model-specific UI code.
- Media subjects can execute installed capabilities and refresh pending canonical results in place.
- Remaining: asynchronous progress/cancellation for long-running engines, category-aware retention, lifecycle recovery/update operations, migration hardening and final release-candidate validation.

## Build 15 — Spectrogram and video playback

- Added bounded offline PCM-WAV spectrogram generation and normalized rendering.
- Added canonical time-frequency overlays, click-to-seek and playhead highlighting on the sound spectrogram.
- Added concrete Qt video playback with temporal canonical synchronization.
- Video frame-region compositing and document page rendering remain open.

# Aperture V4 Build Progress

## Build 26 Repair 23 — hierarchical located-media map index

- Adds indexed, zoom-dependent aggregation for all located media assets.
- Uses world, country, province, district, grid, and exact-location layers with administrative-name fallbacks.
- Displays numbered clusters in both raster and integrated vector maps.
- Cluster details separate image, video, audio and capture, subject, user-defined location counts.
- Uses SQLite R-Tree bounds filtering plus composite hierarchy indexes; individual assets are not scanned globally.


Version: 4.0.0.dev1

## Implemented in increment 1

- Stable producer-neutral canonical enrichment contracts.
- SynthesisCore capability request/result boundary.
- In-process capability router with activate, deactivate and removal lifecycle.
- Aperture capability-result translation into pending canonical enrichment.
- Aperture review transitions with durable review events.
- Source registry and source removal defaults preserving accepted enrichment.
- Subject-centric projection for primary subjects and linked observation evidence.
- Manifest V2 fields for capability and source extensions.
- Fresh-schema support for V4 statuses, source snapshots and source records.
- Vertical-slice tests covering execution, translation, review, observation projection, deactivation and source removal.

## Implemented in increment 2

- Existing BioCLIP Tree-of-Life classifier wrapped as a SynthesisCore capability without changing its model-loading implementation.
- BioCLIP output normalized into producer-neutral taxonomy candidates with confidence, rank and external identifiers.
- Bundled deterministic offline sound-event capability for testing time-based enrichment without a large model dependency.
- Sound time-segment translation and timeline projection.
- Generic renderer registry selected by canonical shape rather than producer name.
- Reusable presentation models for taxonomy, labels, spatial overlays, timelines, transcripts, document regions, measurements, relationships, artifacts, provenance and review commands.
- Configurable Minimal, Standard and Research enrichment-retention profiles.
- Deliberate slimming preview and execution that can remove rejected/expired/pending records and diagnostic/vector payloads while preserving accepted enrichment by default.
- Regression tests for BioCLIP normalization, sound projection, renderer selection and accepted-data retention.

## Implemented in increment 4

- Stable source/importer execution contracts and an in-process source router.
- Offline CSV reference importer producing canonical labels, relationships, and measurements.
- Source-result translation into pending Aperture enrichment with compact source snapshots.
- Subject-centric source workspace service for importer execution and projection.
- Durable observation-to-photo/sound/video/document links with automatic accepted-evidence projection.
- Canonical enrichment search by text, subject, shape, status, and source.
- Aggregate reporting by status, canonical shape, and source.
- Portable JSON export retaining accepted value, target, review, producer, licence, attribution, and checksum snapshots.
- Managed offline bundle removal that separates runtime-file deletion from canonical enrichment deletion and preserves accepted knowledge by default.
- Regression tests covering importer execution, observation discovery, search/report/export, and source-file removal.

## Remaining

- Connect the V4 BioCLIP capability adapter to the current GUI worker invocation path.
- Bind generic renderer presentation models to concrete Qt workspace widgets.
- Bind bundle installation/removal and retention actions to concrete Qt controls.
- Complete installer integration and Windows field validation.

## Implemented in increment 3

- Subject-workspace orchestration service that executes a capability, translates results, projects pending enrichment, and reviews the same canonical records.
- Workspace ownership validation prevents review actions from mutating enrichment attached to another subject.
- Producer-neutral dynamic parameter form model with controls, defaults, choices, type coercion, required fields, and numeric range validation.
- Offline extension bundle installer for capability and source packages.
- Safe ZIP extraction with traversal protection.
- Per-file SHA-256 verification before installation.
- Compatibility validation before activation and installation into versioned local directories.
- Aperture source-registry registration with local/offline state, licence, attribution, and aggregate installed checksum.
- End-to-end tests for sound workspace execution/review, parameter validation, and source-bundle installation.

## Implemented in increment 5

- Headless enrichment workspace controller that maps canonical projections to reusable renderer-neutral presentation models.
- Concrete Qt enrichment summary, canonical result list, provenance panel, and accept/reject controls.
- Review actions update the same canonical record through `EnrichmentWorkspaceService`.
- Concrete desktop Enrichment Sources workspace showing installed/offline/removed state and pending, rejected, and accepted record counts.
- Separate source controls for deactivation and removal, with accepted structural enrichment preserved by default and an explicit destructive opt-in.
- Source registry listing and per-status enrichment-count APIs.
- Desktop navigation integration for Enrichment Sources without replacing the existing BioCLIP worker or AI Review queue.
- Headless regression tests for renderer-backed review and source-manager data.

## Remaining after increment 5

- Embed `CanonicalEnrichmentPanel` into the concrete photo, sound, video, document, and observation detail workspaces.
- Route the legacy BioCLIP generation action through the V4 workspace service while retaining the existing worker scheduling and one-writer safety.
- Add concrete bundle installation and retention/slimming dialogs.
- Add broader native importers and complete Windows field validation.

## Implemented in increment 6

- Desktop enrichment composition helper activates the independent V4 canonical store and keeps projection/review usable when no model runtime is loaded.
- Sound, video, and document library workspaces can embed `CanonicalEnrichmentPanel` directly beneath the selected original subject.
- Media selection changes rebind the generic panel by canonical subject type and public ID.
- Deliberate retention controller separates preview from apply and exposes Minimal, Standard, and Research profiles.
- Concrete Qt retention dialog shows deletion/slimming counts before execution and requires an additional warning before accepted enrichment can be deleted.
- Concrete verified offline-bundle installation action reports checksum verification and installation failures.
- Regression coverage for desktop composition, workspace embedding, and retention preview/apply.

## Remaining after increment 6

- Attach the generic panel to Photos and Observation History selections.
- Route worker-completed BioCLIP results through the V4 translation service while retaining one-writer scheduling.
- Wire the new bundle and retention dialogs into the Enrichment Sources workspace.
- Complete Windows GUI field validation and add additional native importer adapters.

## Build 8
- Existing GUI BioCLIP generation mirrors ranked taxonomy candidates into the V4 canonical store.
- Source management directly exposes offline bundle installation and retention/slimming.
- Legacy review and one-writer worker behavior remain intact.

## Build 9

Completed primary subject workspace composition and richer canonical presentation. The desktop now binds canonical enrichment to Photo, Sound, Video, Document, and Observation selections. Spatial, timeline, spectrogram-region, transcript, and document-region renderer payloads are producer-neutral and normalized before Qt presentation.

## Build 10

- Added bundled offline GeoJSON, GTFS, and railML source importers alongside CSV.
- GeoJSON normalizes spatial features into canonical bounding boxes or relationships.
- GTFS normalizes stops into relationship candidates with coordinates and external IDs.
- railML normalizes operational points into relationship candidates.
- Added one built-in source-router factory for discovery and activation of all local importers.
- Registered bundled importers as locally available offline sources during desktop startup.
- Added a concrete Source Management import action that selects an importer, local package, target subject, and canonical GeoJSON output shape.
- Imported records enter the shared pending-review, provenance, projection, retention, and removal lifecycle.

## Build 12

- Bidirectional temporal media synchronization contract implemented.
- Complete source-state presentation and action eligibility implemented.
- Safe count-based removal preview and provenance visibility implemented.
- Automated validation: 139 passed, 1 skipped where PySide6 is unavailable.

## Build 13

- Real photo viewer now receives the shared canonical enrichment controller.
- Canonical boxes and polygons render in the image scene rather than a detached preview only.
- Image and canonical-panel region selection are synchronized in both directions.
- Async preview loading retains pending overlay scenes until the pixmap is ready.
- Validation: 143 passed, 1 skipped where PySide6 is unavailable.

## Build 19

Recoverable source lifecycle and asynchronous capability execution are implemented. Sources can be verified, marked missing, relinked, recovered and superseded with durable audit history. Generic capability runs no longer block the Qt event loop and expose progress/cancellation state.


## Build 20

Lifecycle edge cases and asynchronous execution were hardened for the clean-start release baseline. Full validation: 165 passed, 1 skipped because PySide6 is unavailable. Remaining work is consolidated release-candidate verification and Windows testing.

## Build 21 — Test Release Candidate

All in-scope clean-start implementation work is complete. Release verification now enforces version consistency, required Windows entry points, exact deterministic package inventory, exclusion of runtime artifacts, source-tree preflight and extracted-archive preflight. Migration and backward compatibility remain intentionally deferred to future post-launch builds. Final Windows field validation remains external to automated Linux validation.


## Build 22 — Windows preflight correction

Fixed the self-invalidating Windows installer preflight discovered during installation testing. Full suite: 169 passed, 1 skipped on the Linux validation host.


## Build 26

Windows startup repair: empty V4 libraries with incomplete physical schemas are archived and reconstructed safely.

### Repair 19

- Document workspace: native PDF/Markdown/TXT display retained and expanded.
- Office/OpenDocument assets: delegated to the system file association.
- Import routing expanded to common Word, Excel, PowerPoint, and OpenDocument extensions.
- No LibreOffice or Microsoft Office runtime is bundled; missing associations produce an actionable message.
## Build 27

Completed the task-oriented navigation pane, matching menu bar and toolbar, distinct About Aperture menu, and staged Shutdown progress UI.


## Build 33.3
Adds offline YOLO 11 detection/segmentation and Segment Anything ViT-B model providers.
