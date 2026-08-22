## Fieldora 0.11.14 — Thumbnail Recovery Repair

- Keeps derivative cache states within the persisted schema contract.
- Restarts idempotent completed thumbnail jobs when their cache artifact is
  missing, without producing duplicate repair records.
- Repairs failed and stale thumbnail backlogs in the background.

## Fieldora 0.11.13 — Offline OpenSeaMap Overlays

- Imports prepared transparent raster MBTiles nautical overlays as verified,
  independently managed offline packages.
- Composes OpenSeaMap seamarks over raster and vector basemaps without contacting
  public tile servers.
- Runs validation and copying through Activity Center and preserves attribution,
  licence and reference-only navigation warnings.

## Fieldora 0.11.12 — Governed Deletion Approvals

- Added person/function deletion routing and administrator fallback.
- Added pending server approval and decision controls to Trash.
- Added durable audit and backup coverage for deletion requests.

## Fieldora 0.11.11 — Recognizable Native Process Names

- Added seven purpose-named frozen Windows executables.
- Added Windows version and product metadata to every executable.
- Renamed the native setup and installed shortcut surface to Fieldora.

## Fieldora 0.11.10 — Non-blocking Thumbnail Pipeline

- Removed original-image decoding and derivative writes from gallery workers.
- Added visible background thumbnail state and five-second cache polling.
- Paused gallery thumbnail checks outside the active screen.
- Moved startup reconciliation to a delayed daemon task.

## Fieldora 0.11.9 — Maritime Research Logs and Depth

- Moved Maritime Operations into Research.
- Added dedicated Submarine Logs.
- Added migrated depth-in-metres storage, registration, display and export.
- Added an explicit buddy field to dive records.

## Fieldora 0.11.8 — Home Navigation Startup Hotfix

- Fixed the Home navigation tuple shape that blocked desktop startup.
- Added a navigation-tree structure regression check.

## Fieldora 0.11.7 — Home Dashboard and Calendar Visibility

- Added the Fieldora Home research dashboard and made it the startup workspace.
- Added scheduled-day highlighting and activity-count badges to both calendars.
- Added `.ics`, Google Calendar and Outlook event handoff support.

## Fieldora 0.11.6 — Marine Science and Maritime Operations

- Added separate Marine & Freshwater Science and Maritime Operations workspaces.
- Added typed records, media attachment links, audit history and domain export.
- Added independent module switches and navigation integration.

## Fieldora 0.10.16 — assigned review, multi-enrichment, OCR, and PDF navigation

- Added audited user-assigned AI review queues across photo and canonical media
  review.
- Aligned AI Review visibility with enabled Library types.
- Added concurrent multi-capability enrichment selection and independent
  progress screens.
- Added installable offline PDF OCR using PyMuPDF and RapidOCR ONNX.
- Added continuous multi-page PDF scrolling and page navigation.

## Fieldora 0.10.15 — parallel multi-library analysis

- Added bounded parallel multi-file capability execution across all media
  libraries.
- Added dedicated per-library batch screens with item-level state and
  cancellation.
- Bound analysis-screen activation and cancellation to Library Types settings.

## Fieldora 0.10.14 — Excalidraw React initialization fix

- Fixed React error 185 caused by the save debounce timer updating component
  state and recreating Excalidraw's change callback.
- Made the document bridge and save callback stable for the editor lifetime.
- Preserved packaged local-asset CSP permissions in the Excalidraw source build.

## Fieldora 0.10.13 — Excalidraw runtime fix

- Allowed packaged local Excalidraw assets under the offline CSP.
- Added visible page-load, JavaScript, and editor-initialization diagnostics.

## Fieldora 0.10.12 — Offline Manuals application

- Added a standalone searchable Installation, Administrator, and User manuals app.
- Added Fieldora Help-menu and GUI launcher integration.

## Fieldora 0.10.11 — Excalidraw startup hotfix

- Fixed the missing `QListWidgetItem` Qt import that prevented desktop startup.

## Fieldora 0.10.10 — Phase F certification workflow

- Added a nine-exercise machine-readable live-certification plan.
- Added fail-closed same-environment evidence status assessment.

## Fieldora 0.10.9 — Phase F audit-export administration

- Added SQLite/PostgreSQL tenant audit export from authoritative access repositories.
- Added mandatory source-chain verification and independent archive verification.

## Fieldora 0.10.8 — Phase F secret-rotation administration

- Added SQLite/PostgreSQL external-secret version coordination.
- Added conflict-safe stage, activate, and status operator commands.

## Fieldora 0.10.7 — Phase F retention administration

- Added PostgreSQL retention claims with skip-locked concurrency and fencing tokens.
- Added legal-hold and retention operator commands with SQLite parity.

## Fieldora 0.10.6 — Phase F tenant governance administration

- Added SQLite/PostgreSQL operator commands for quota administration.
- Added tenant-scoped usage and decimal cost reports.

## Fieldora 0.10.5 — Phase F production recovery contract

- Added machine-verifiable RPO/RTO, PostgreSQL PITR, object recovery, key custody,
  legal-hold, and restore-drill requirements.
- Added a reference recovery declaration and assessment CLI.

## Fieldora 0.10.4 — Phase F graceful rollout lifecycle

- Added coordinated signal handling and API drain-before-stop behavior.
- Workers stop claiming work after termination and finish the active fenced job.
- Added orchestration grace periods for API and worker shutdown.

## Fieldora 0.10.3 — Phase F production readiness

- Added distinct liveness, startup, and dependency-readiness endpoints.
- Added PostgreSQL, object-storage, and OpenSearch readiness checks.
- Updated orchestration probes to drain unready replicas without causing restart
  storms.

## Fieldora 0.10.2 — Phase F shared production runtime

- Added S3-compatible storage for governed export payloads.
- Configured workers to use shared production repositories and continuous polling.
- Hardened container construction and build-context exclusions.

## Fieldora 0.10.1 — Phase F certification evidence hardening

- Added verified artifact capture for live failure and recovery exercises.
- Rejects evidence tampering, duplicate exercise records, and mixed certification
  environments.
- Replaced the fixed container base with a build-time image reference suitable for
  digest pinning by the release environment.

## Fieldora 0.10.0 — Phase F deployment foundation

- Added the production deployment assessment contract and reference topology.
- Required high-availability, recovery, TLS, external-secret, and rolling-upgrade
  declarations before a topology is configuration-ready.
- Separated configuration readiness from live production certification.
- Added tenant quotas, usage accounting, retention fencing, legal holds, audit
  export, external-secret rotation, operational evidence, and security runbooks.

## Fieldora 0.09.10 — automatic embedded Excalidraw

- Automatically creates and opens `Drawing 1` on first use.
- Automatically displays an existing drawing when the workspace opens.
- Added explicit Excalidraw version, licence, and acknowledgement information to
  the About Center and diagnostics.

## Fieldora 0.09.9 — full offline Excalidraw

- Bundled Excalidraw 0.18.1 and its complete self-hosted asset set.
- Added the network-blocked Qt WebEngine editor and atomic Documents bridge.
- Replaced external application opening with in-Fieldora editing and autosave.

- Aligned splash, descriptions, project link, icon filename, and launcher links.
- Replaced the active custom whiteboard with `.excalidraw` Documents and snapshots.
- Added no-migration compatibility guidance and documentation alignment evidence.

## Fieldora 0.09.6 — Phase E cryptographic lifecycle and exit gate

- Added AES-256-GCM encryption and Ed25519 signatures for governed packs.
- Enforced signed expiry metadata before decryption and disclosure.
- Added durable revocation state, content-key destruction, and encrypted-envelope
  removal.
- Added the passing deterministic Phase E exit-gate report.

## Fieldora 0.09.5 — Phase E governed project data packs

- Added canonical server-generated project pack and delta manifests.
- Filtered records, fields, and tombstones before any package bytes are written.
- Added deterministic payload checksums and exact delta-base validation.
- Installed governed data only in the isolated desktop pack cache and registry.

## Fieldora 0.09.4 — Phase E contribution and conflict review

- Added explicit contribution previews covering updates, deletions, and record types.
- Required durable license and contract-term acknowledgment for the current enrollment
  revision before any push.
- Added single-use keep-local, accept-remote, and manual conflict resolutions.
- Added a Qt contribution/conflict review panel over application services.

## Fieldora 0.09.3 — Phase E HTTP and resumable media synchronization

- Bound pull/push synchronization to strict versioned `/api/v1` JSON requests.
- Injected machine authentication without persisting credentials in protocol records.
- Added durable ranged-media checkpoints with ETag continuity and SHA-256 completion.
- Reconciled post-crash partial files to the last committed offset before resuming.

## Fieldora 0.09.2 — Phase E pull/push protocol coordinator

- Added versioned, transport-neutral pull/push protocol contracts.
- Connected durable journals to applied, duplicate, retry, rejection, and conflict
  server outcomes.
- Advanced pull cursors only after durable page acceptance and preserved safe replay.
- Isolated claims per enrollment and blocked transport when rights are revoked.

## Fieldora 0.09.1 — Phase E revision synchronization journal

- Added durable push outbox and pull inbox journals with idempotency keys.
- Added bounded leasing, deterministic interrupted-work recovery, retry scheduling,
  and terminal completion state.
- Added per-enrollment pull cursors, tombstone transport, and conflict persistence.
- Blocked new contributions when project rights are expired or revoked.

## Fieldora 0.09.0 — Phase E desktop synchronization foundation

- Added HTTPS platform endpoint and desktop account contracts.
- Added durable device registration and revision-guarded project enrollment state.
- Added a default-deny effective-rights view for revoked, expired, or
  unacknowledged enrollments.
- Added core migration 31 and Phase E foundation regression coverage.
- Preserved the photo-gallery scroll debounce and path-aware search repairs.

## Fieldora 0.08.34 — Phase D exit-gate evidence audit

- Added a fail-closed, machine-readable Phase D gate evaluator.
- Mapped policy-boundary and recovery outcomes to deterministic test evidence.
- Kept the phase exit conditional pending live-provider and installed-client
  certification.

## Fieldora 0.08.33 — PostgreSQL access-control parity

- Added PostgreSQL identity, authentication, PBAC, contract, and audit persistence.
- Serialized concurrent hash-chain audit appends with an advisory transaction lock.
- Completed the planned PostgreSQL repository adapter set.

## Fieldora 0.08.32 — PostgreSQL Science repository

- Added PostgreSQL Science records and snapshot persistence.
- Preserved optimistic revisions and atomic snapshot saves.
- Unified API, search rebuild, and project export jobs over the selected Science source.

## Fieldora 0.08.31 — PostgreSQL governed-export metadata

- Added PostgreSQL export lifecycle and attestation metadata.
- Added conditional revocation and single-writer attestation updates.
- Added skip-locked expiry cleanup claims for independent maintenance workers.

## Fieldora 0.08.30 — PostgreSQL governed-media metadata

- Added PostgreSQL media and resumable-upload metadata repositories.
- Added atomic upload completion and optimistic offset enforcement.
- Kept object bytes behind the existing filesystem/S3 storage boundary.

## Fieldora 0.08.29 — PostgreSQL distributed-job repository

- Added a PostgreSQL job adapter using atomic skip-locked claims.
- Preserved renewable fenced leases across SQLite and PostgreSQL implementations.
- Added optional dependency and bounded DSN-file configuration.

## Fieldora 0.08.28 — External OpenSearch projection

- Added an optional HTTPS OpenSearch-compatible adapter with atomic alias rebuilds.
- Added bounded query/result handling and token-file authentication.
- Preserved per-candidate PBAC filtering before search disclosure.

## Fieldora 0.08.27 — Fenced independent job workers

- Added worker-owned, renewable leases with unique fencing tokens.
- Added bounded independent worker execution and stale-worker result rejection.
- Added the server-jobs schema migration while retaining queued work.

## Fieldora 0.08.26 — Trusted OIDC discovery and signing-key refresh

- Added HTTPS OpenID Connect discovery with exact issuer validation.
- Added bounded JWKS caching and one unknown-key refresh for provider rotation.
- Preserved explicit local identity mapping and PBAC as the authorization boundary.

## Fieldora 0.08.25 — Restored-root startup and upgrade validation

- Added offline migration and complete server composition for recovery copies.
- Added mandatory subsystem and post-migration integrity checks.
- Added atomic machine-readable readiness reports.

## Fieldora 0.08.24 — Verified one-node recovery

- Added coordinated server database and local-object backup bundles.
- Added exact manifest, checksum, and SQLite-integrity verification.
- Added non-destructive restore drills to a new server data root.

## Fieldora 0.08.23 — TLS-enabled one-node server

- Added direct HTTPS serving with TLS 1.2 minimum and HSTS.
- Made non-loopback listeners fail closed without TLS.
- Added explicit trusted-terminator override and certificate configuration checks.

## Fieldora 0.08.22 — S3-compatible governed media storage

- Added replaceable filesystem and S3-compatible media-object adapters.
- Preserved PBAC-gated opaque media IDs and byte-range delivery.
- Added optional S3 server configuration without credential command-line arguments.

## Fieldora 0.08.21 — Governed contract expiry reminders

- Added a bounded, per-record PBAC-filtered expiring-contract queue.
- Added configurable 1–365 day expiry review windows.
- Added an accessible Expiring workspace to the server web client.

## Fieldora 0.08.20 — Delegated contract approval queue

- Added a cursor-bounded, per-record PBAC-filtered approval queue.
- Separated contract approval discovery from contract administration rights.
- Added an accessible Approvals workspace to the server web client.

## Fieldora 0.08.19 — Contract approval quorums

- Added bounded multi-approver quorums with distinct-identity enforcement.
- Kept proposed contracts non-authorizing until the final approval.
- Added approval progress to the server web client and API response.

## 4.0.0.dev1+build28.4.repair2

- Fixed managed-copy deletion failing on import-plan foreign keys.
- Added bulk removal by selection, directory, and drive with safety preflight.
- Preserved linked observations and all catalog enrichment while reclaiming managed storage.

## 4.0.0.dev1+build28.4.repair2

- Repaired Linked-to-Hybrid conversion: existing linked source instances are reused while a managed library copy is added.
- Prevented UNIQUE constraint failures on file_instances.path_key during storage conversion.
- Added regression coverage for linked source to managed-copy conversion.

# Build 28.4 — Observation provenance completion

- Added immutable initial-observation provenance to storage locations.
- Added follow-up source registration for matching content at new locations.
- Added multi-source original resolver using consolidated device availability.
- Added migration of existing source records and one-initial-per-asset enforcement.

Aperture Build 28.3 — Consolidated Device Availability

Build 28.3 introduces a library-wide storage_devices.db registry. Device mount state is maintained once per persistent volume UUID, while individual observations retain device/location references and relative paths. Offline status is derived from the registry; per-file verification is reserved for online devices and explicit checks.


## Build 28 — Original storage policy

Build 28 introduces Flexible Storage Architecture as a distinct development milestone. Imports now offer Managed, Linked, and Hybrid original-storage policies. Users may create an Aperture-owned original, work from the source original in place, or retain both. The selected policy is remembered for future imports. Enrichments remain attached to the stable asset identity rather than a physical copy, and the inspector separately reports storage mode, availability, source file, and Aperture original. Linked imports avoid full-size duplication while retaining thumbnails, metadata, locations, and enrichments.


## 4.0.0.dev1+build27.repair4

- Retained the latest vector-map overlay payload in Qt and replayed it after QWebEngine navigation completes.
- Restored Aperture media, observation, site, and track layers after asynchronous offline-style and package loads.
- Added idempotent foreground restoration, delayed retries, and renderer overlay diagnostics.
- Fixed geotagged media markers appearing on the clean basemap but disappearing when an offline vector package was active.


- Clean-install reissue: Trash Manager now uses the canonical `file_instances.normalized_path` schema, loads only when opened, and cannot block application startup if its query fails.

## Build 27 Repair 3 — Dedicated Trash Manager

- Removed **Delete permanently** from Library and Collections galleries.
- Added **Tools & Resources → Trash Manager**, a table-based maintenance workspace that avoids thumbnail decoding and gallery layout work.
- Restore and permanent deletion run in a background worker with progress reporting.
- Permanent deletion is limited to assets already in Trash and retains explicit handling for linked observations.
- The gallery remains focused on fast curation: its destructive action is now only **Trash**.

## 4.0.0.dev1+build27.repair3

- Made raster and vector map overlay ordering explicit so media clusters remain above offline basemaps.
- Reasserted MapLibre overlay sources and foreground layers after style loads, style changes, package changes, zooming, and panning.
- Added regression coverage for raster z-order and vector foreground restoration.

## 4.0.0.dev1+build27.repair1

- Removed the unused inspector preview panel.
- Expanded multi-selection metadata editing to match the single-photo editor, including tags and subject geolocation.
- Made map media queries independent of stale R-Tree entries so located assets remain visible.
# Aperture 4.0.0.dev1 Build 27

- Reorganized the navigation pane into Library, Library Management, Observations, Knowledge, Tools & Resources, and Settings.
- Reorganized the menu bar and toolbar around the same task-oriented structure while preserving existing workspace routes and workflows.
- Kept About Aperture as a distinct top-level menu.
- Renamed Quit to Shutdown and added a visible staged shutdown progress dialog for backups, workers, state saving, and resource release.

# Aperture 4.0.0.dev1+build26.repair22

- Fixed offline photo overlays by matching the spatial database query to the full five-by-five raster canvas.
- Added regression coverage for photo locations near every visible canvas edge.

# Aperture 4.0.0.dev1+build26.repair21

- Fixed Office Open XML and OpenDocument imports being rejected as generic ZIP archives.
- ZIP-signature rejection now exempts all recognized document formats while continuing to reject unknown archive containers.
- Added regression coverage for DOCX, XLSX, PPTX, ODT, ODS, and ODP families.

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

## 2026-07-24 — Collapsible library detail panels

- Implemented a persistent one-line collapsed state for the lower canonical enrichment/review panel in Photos, Sounds, Videos, and Documents.
- Preserved the existing widget instance and operational state while folded.
- Did not alter import, enrichment, model execution, review, storage, viewer, or export logic.

## 4.0.0.dev1 Build 26 Repair 16 — Field-validation documentation update

- Recorded successful operation of all tested import functions.
- Recorded functioning canonical enrichment.
- Recorded the export failure at progress 2 of 4: `'str' object has no attribute 'value'`.
- Clarified that the video import path works, while the video-model processing path is not yet functioning correctly.
- Recorded that other tested model functions are functioning.
- Added `FIELD_VALIDATION_STATUS.md` and corrected the first-read release identity to Build 26 Repair 16.

## 4.0.0.dev1 Build 26 Repair 15

- Added selectable photo, RAW, sound, video, and document import routing.
- Added installable test-subject providers for MegaDetector 6, BioCLIP 2, Perch 2, BatDetect2, and BioCLIP 2.5 Huge.
- Marked resource downloads and native Windows operation as requiring field validation.

## 4.0.0.dev1 Build 26 Repair 14

- Added on-demand BirdNET sound/video identification and SpeciesNet photo/video wildlife review.
- Added isolated dependency installation, model acquisition, health checks, checksums, activation,
  cancellation, and persisted capability restoration through the Models workspace.

## 4.0.0.dev1 Build 26 Repair 13

- Fixed Windows installation failure when a new Aperture Library is placed directly beneath an
  existing drive root.
- Added a Windows installer regression that prevents unconditional `New-Item` calls against drive
  roots such as `D:\`.

## 4.0.0.dev1 Build 26 Repair 12

- Corrected Windows environment recreation under Conda 26 by keeping removal on the explicit
  conda-forge-only channel policy.
- Prevented the installer from requiring acceptance of unused Anaconda default-channel terms.
- Added regression coverage and repeated the complete Linux acceptance cycle.

## 4.0.0.dev1 Build 26 Repair 11

- Closed the Linux installation, clean-library, GUI lifecycle, persistence, repair, and rollback
  acceptance cycle.
- Made Linux runtime publication transactional and preserved the prior runtime on staged failure.
- Corrected library identity, subsystem database isolation, Qt thread shutdown, and lock cleanup.
- Reconciled the Python 3.11 dependency constraints used by clean installations.

## 4.0.0.dev1 Build 26 Repair 3

- Validate the physical SQLite table-and-column contract instead of trusting only migration ledger rows.
- Compile core repository queries before desktop construction, including the observations query that exposed the startup failure.
- Return the production database connection factory after lifecycle validation.
- Expand Windows installation verification to create, reopen, and query a temporary clean library.
- Add regression coverage for a missing `observations` table with an otherwise complete migration ledger.

# Build 26

- Added structural schema validation during library opening.
- Added safe reconstruction of empty incomplete clean-start libraries.
- Preserved damaged databases before repair and refused destructive repair when user data exists.
- Added regression coverage for a missing `observations` table after a recorded migration sequence.

# Build 25

- Fixed startup failure when a persisted clean-start subsystem database was created by an earlier development build with a different immutable migration checksum.
- Incompatible subsystem databases are archived with their SQLite sidecars and diagnostic metadata before a fresh current-schema store is created.
- Added exact regression coverage for `MigrationError: checksum mismatch for migration 1`.

# Build 24

- Corrected Windows preflight exclusion for `FieldoraData-V5`.
- Changed the clean-start default library folder to `Fieldora-Library-V5`.

## Aperture 4.0.0.dev1 Build 23 — Clean-start identity correction

- Corrects the active startup splash from the legacy V3.RC1F6 label to Aperture 4.0.0.dev1.
- Uses a separate FieldoraData-V5 runtime root.
- Ignores launcher selections written by pre-V4 launcher schemas.
- Creates a clean V4 default library when no explicit library is supplied.
- Keeps migration disabled and gives a clear error when a legacy library is selected manually.

## 4.0.0.dev1 Build 22

- Fixed Windows deployment preflight running after mutable ApertureData creation.
- Excluded the complete ApertureData runtime tree from release inventory verification.
- Added regression tests for preflight ordering and default runtime data coexistence.

# Aperture 4.0.0.dev1 Build 18

- Added category-specific canonical enrichment retention counters.
- Preserved OCR text and geographic assertions while removing configured OCR intermediates and source-package references.
- Added explicit reproducibility-impact reporting.
- Added durable `enrichment_retention_audit` records for applied slimming operations.
- Expanded the retention dialog preview with per-category deletion counts and accepted-record preservation.
- Added Build 18 regression coverage for Minimal and Research retention behavior.

# Aperture 4.0.0.dev1 Build 17

- Added input-kind filtered capability discovery for subject workspaces.
- Added producer-neutral manifest parameter validation and normalization.
- Added a manifest-driven Qt execution dialog with generated string, choice, integer, floating-point and boolean controls.
- Added optional structured JSON input for capabilities that accept explicit structured events or records.
- Connected Sounds, Videos and Documents to generic capability execution and immediate canonical result refresh.
- Added Build 17 regression coverage for discovery, validation, execution and desktop wiring.

# Aperture 4.0.0.dev1 Build 16

- Added a reusable transparent normalized overlay canvas for video and document surfaces.
- Composited canonical bounding boxes and segmentation polygons directly over video playback.
- Added bidirectional region selection and playback-position highlighting for video overlays.
- Added local PDF page rendering through Qt PDF with page-relative canonical overlays.
- Added a graceful document-preview fallback when Qt PDF is unavailable.
- Added Build 16 regression coverage for video and document overlay composition.

# Aperture 4.0.0.dev1 Build 15

- Added a bounded standard-library PCM WAV spectrogram transform.
- Added an interactive Qt spectrogram canvas with canonical time-frequency overlays and playback cursor synchronization.
- Added concrete Qt video playback with play/pause, seek, position, duration and missing-file reporting.
- Connected canonical temporal selections to the video player and video playhead updates to canonical highlighting.
- Added Build 15 regression coverage for normalized spectrogram output and viewer composition contracts.

# Aperture V4 Build 7

- Strengthened the Windows installer launch experience with separate normal and debug shortcuts.
- Debug sessions now capture timestamped console output, environment metadata, structured logs, launcher logs, installation metadata, and exit status.
- Debug sessions automatically produce a portable support ZIP for field-test issue reports.
- Verified uninstall cleanup for normal, debug, Start Menu, and launcher assets without removing libraries or accepted enrichment.


## 3.0.0rc1.post9 — Dynamic on-demand model plugins

- Added external `models.json` metadata catalog and optional `aperture.models` entry-point discovery.
- Added runtime dependency checks and isolated on-demand pip installation without restarting Aperture.
- Added catalog-key provider loading while retaining BioCLIP as the default existing execution path.
- Added deterministic unload, garbage collection, CUDA cache cleanup, and optional runtime deletion.
- Added a Models settings workspace with dynamic parameter controls.
- Added generic canonical-enrichment mapping for newly registered models.

## 3.0.0rc1.post8 — Unified OSM composition and Export/Reporting separation

- Replaced single-winner regional vector tile selection with feature-layer composition across every intersecting enabled OpenStreetMap extract.
- Merges same-named MVT layers, remaps feature tag dictionaries, and preserves the global XYZ coordinate grid so adjacent regions render as one map at their declared zoom levels.
- Uses tile-envelope intersection rather than tile-center ownership, preventing edge regions from disappearing.
- Renamed the former Reporting-and-export screen to **Export** and added a separate top-level **Reporting** workspace.
- Added File → Export (Ctrl+E) and File → Reporting (Ctrl+Shift+E).
- Fixed BioCLIP AI Review acceptance for valid label-only suggestions that are not linked to an installed taxonomy record; they now move from pending to accepted and create canonical Aperture-owned enrichment without fabricating an observation.
## Reporting, export, and multi-database recovery architecture

- Approved top-level Reporting with contextual report generation from observations, media, and collections.
- Separated Asset Export, Data Export, and Generate Report while sharing a permission-aware package builder.
- Added optional original photo, sound, video, and document inclusion with unavailable-original reporting.
- Defined complete, active-type, and custom multi-database backups for Aperture-owned databases.
- Excluded BioCLIP and other integration runtimes while retaining accepted normalized enrichment.
- Fixed deployment preflight so generated `.installation` reports and legacy `preflight.json` entries cannot invalidate a release during verification.


## Built-in media workspaces

- Renamed the duplicated Library navigation child to **Photos**.
- Added independent **Sounds**, **Videos**, and **Documents** Library screens.
- Added medium-specific metadata displays for audio recording, video capture, and document properties.
- Connected workspace visibility to Settings > Library Types; hiding a type does not delete its assets or metadata.
- Kept each non-photo screen on an independent read-only query worker.
## 3.0.0rc1.post6 — Aperture V3.RC1F6

> Release 3 implementation scope: no legacy-library data migration or compatibility backfill is included unless separately approved. The new structures are created for fresh Release 3 data while existing RC1 functions continue through their existing repositories.

## RC1F6 regression-safe workspace baseline

- Restored the proven Knowledge Base and BioCLIP Review screen-loading path from the last known-good Aperture V3 Final build.
- Retained the RC1F6 offline-map Activity Center scheduling, bounded worker execution, enrichment history, review actions, subject-location, and relationship-enrichment changes.
- Removed the experimental per-view QThread refresh wrappers that were introduced after the known-good build and correlated with immediate Windows 11 GUI stalls.
- BioCLIP Review keeps the RC1F6 actions: Accept, Accept All Pending & Next, Accept Only & Next, rejection, defer, and reversible enrichment acceptance.
- Release-manifest and deployment-preflight verification are regenerated from the final package.


- Added safe legacy path/data discovery and cleanup tooling.
- Added selected-disk installation configuration at `config/installation.json`.
- Protected current data root and shared third-party caches from accidental removal.

## 3.0.0rc1.post2 — V3.RC1F2

- Added responsive branded startup splash using the packaged Aperture logo.
- Added real weighted milestone progress during blocking desktop construction.
- Reused one QApplication for splash and main window.
- Added startup-splash-visible telemetry.

## 3.0.0rc1.post1 — V3.RC1F1

- Added a NatureAI-owned engine-state database and an Aperture bridge handshake.
- Full AI installation now records BioCLIP, TreeOfLifeClassifier, TreeOfLife-10M, device, and readiness as one activated NatureAI engine.
- Aperture libraries discover the ready NatureAI engine at startup and create only non-owning provenance bridge records.
- AI Resources now reflects the active NatureAI engine without requiring duplicate model ownership or GBIF/CSV resources.
- Tree-of-Life classification accepts the managed NatureAI prompt profile and no longer requires a local model artifact path.

# Aperture V3.RC1F1 — Integrated NatureAI release candidate

Version **3.0.0rc1.post1** promotes the completed Build 3.336 stabilization work into the first Version 3 release candidate.

## NatureAI engine

- BioCLIP, `pybioclip==2.1.5`, `TreeOfLifeClassifier`, the original BioCLIP v1 model identity, and the matching Tree-of-Life resources are installed and validated as one engine.
- Initial Full AI installation primes the Tree-of-Life classifier and activates it automatically; a CSV and GBIF are not required for the original NatureAI classification path.
- Aperture taxonomy prompt sets remain supported as optional bounded or custom classifiers. Empty prompt sets are not accepted as ready.
- GBIF remains an independent taxonomy/enrichment component and may resolve or enrich NatureAI results without being a prerequisite for inference.
- Maintenance Center can download, resume, import, validate, repair, and reactivate the complete NatureAI/BioCLIP environment.

## Knowledge Base and workspaces

- Knowledge Base exposes BioCLIP/NatureAI, GBIF taxonomy, and reference resources as independent components.
- Library and Collections retain independent workspaces, splitter state, and inspector containment.

## Upgrade notes

Install over the approved prior release, then run **Maintenance Center → Repair Full AI / NatureAI Engine** when upgrading an existing environment. Confirm **Tree of Life classifier: Ready** before starting AI Review. Existing libraries and GBIF databases are not replaced.

## Release identity

- Product release: **Aperture V3.RC1F1**
- Python package version: **3.0.0rc1.post1**
- Baseline implementation: Build 3.336 post22

---

## 2.0.0rc3.post21

- Restored legacy NatureAI TreeOfLifeClassifier inference as a fallback independent of GBIF/CSV taxonomy resources.
- Added pybioclip 2.1.5 to the AI dependency profile.
- Added provenance identifying the classification source.

## 2.0.0rc3.post19 — Local BioCLIP import and Maintenance Center resource setup

- Added complete BioCLIP folder import and offline activation.
- Added BioCLIP download/import controls to the standalone Maintenance Center.
- Redesigned the Maintenance Center as a scrollable, viewport-safe screen.

# Build 3.336 post18 — Legacy BioCLIP flow restoration and GBIF schema reconnection

- Uses the completed GBIF importer database and its `taxa`/`taxon_names` schema exclusively.
- Adds explicit taxonomy-root discovery and schema diagnostics; obsolete `names` queries are removed.
- Restores the proven BioCLIP setup sequence while retaining component enable/disable controls.
- Downloads the official BioCLIP checkpoint through the resumable Hugging Face cache first, with the direct range downloader only as fallback.
- Pins the verified BioCLIP model revision and adds `huggingface-hub` to the AI installation profile.

## Build 3.336 BioCLIP resource audit (post17)

- Pinned the official original Imageomics BioCLIP paper model revision instead of following a mutable upstream main branch.
- Added a signed resource descriptor containing repository, revision, OpenCLIP architecture, and checkpoint SHA-256.
- OpenCLIP now verifies the installed checkpoint before inference and rejects mismatched architectures.
- Added reusable BioCLIP installation audit diagnostics; legacy unpinned installs are reported as requiring repair.

# Build 3.336 post16 — Component reconnection correction

- Reconnects Knowledge Base · GBIF to the independent database published by the completed Darwin Core importer through `sources.json`.
- Supports the importer schema (`taxa` + `taxon_names`) while retaining legacy `names` compatibility.
- Restores BioCLIP/OpenCLIP as an independently switchable AI engine without deleting models or prior suggestions.
- Adds Settings → Resource Components with persistent GBIF and BioCLIP enable/disable controls and diagnostics.
- Keeps enrichment asset-oriented so photos work now and future media types can reuse the same link/provenance layer.

# Build 3.336 — Knowledge Base Architecture

- Adds Knowledge Base as an independent top-level workspace.
- Moves BioCLIP AI Review and independent GBIF taxonomy enrichment into dedicated Knowledge Base tabs.
- Adds a searchable full-data view across AI suggestions and applied external taxonomy records.
- Preserves legacy AI Review and Taxonomy navigation routes as deep links.
- Persists Knowledge Base splitter geometry independently from Library and Collections.
- Keeps the Library focused on photo management while enrichment remains explicit and auditable.

# Build 3.335 — Independent Library and Collections workspace foundation

This increment implements the highest-risk Phase 1 corrections from the Build 3.335 specification:

- persistent, separately instantiated Library and Collections workspaces
- independent splitter object names and QSettings keys
- safe splitter-state restoration with zero-width rejection
- bounded, scrollable inspector containment
- activate/deactivate workspace lifecycle without reconstruction
- guarded catalog refresh to prevent recursive refresh loops
- navigation through QStackedWidget.setCurrentWidget
- regression coverage for workspace separation and containment

The map renderer, normal photo importer, Darwin Core importer, and independent taxonomy database architecture are unchanged.

Validation: 23 tests passed.

# Build 3.334 — Restore Library and Collections panels

- Restored `ui/qt/library.py` to the last known-good pre-taxonomy-panel implementation.
- Removed taxonomy-workspace signals that changed the active Library and Collections views.
- Kept the independent GBIF Taxonomy workspace as a separate top-level workspace.
- Preserved photo-only Library import and the loopback MBTiles renderer.

### BioCLIP acquisition reliability
- Renamed the normal AI download option to the complete supported BioCLIP model and explicitly distinguished it from the 92 TB occurrence corpus.
- Added cancellable downloads that retain partial data for immediate range-resume.
- Reduced retry lockout delays and increased transfer block size while throttling UI progress updates.

## 3.0.0rc1.post3 — Aperture V3.RC1F3

- Fixed pybioclip Tree-of-Life candidates being rejected when their external identifiers were not present in Aperture's local taxonomy.
- Tree-of-Life scores are retained as raw model scores rather than incorrectly marked as calibrated probabilities.
- Preserved complete upstream classifier rows in suggestion provenance for later GBIF/local-taxonomy resolution.
- Added installer-selected `DataRoot` storage for models, caches, logs, component databases, launcher state, taxonomy packages, maps, and update data.
- Redirected Hugging Face and Torch caches to the selected Aperture data disk.

## 3.0.0rc1.post6 — Activity Center map scheduling fix

- Bounded concurrent offline-map workers through the existing Activity Center.
- Durable queued activities with automatic oldest-first promotion.
- Terminal-state-only installed-map refresh to prevent Qt event-queue flooding during large batches.
- Preserved independent map databases, atomic publication, cancellation, retry, and existing menu behavior.

### Fixed

- Prevented an immediate Windows “Not Responding” state when entering AI Review by moving initial review queries and suggestion-detail queries off the GUI thread.
- Coalesced overlapping AI Review refresh requests while preserving filters, pagination, review actions, preview loading, and existing provider behavior.
- Replaced the normal console-backed Windows launcher shortcut with a hidden Windows Script Host launcher; the Debug launcher remains unchanged.

## RC1F6 Knowledge Base responsiveness correction

- Moved the All Knowledge SQLite projection off the Qt event thread.
- Added read-only/query-only database connections with bounded busy handling for Knowledge Base searches.
- Removed eager Knowledge Base data loading during widget construction.
- Coalesced overlapping refresh requests and prevented duplicate tab-activation refreshes.
- Chunked Knowledge Base table population so rendering large result sets yields to the Qt event loop.

## Release 3 architecture foundation — media and integrations

- Added default-enabled Photographs, Sounds, Videos, and Documents Library capabilities.
- Added shared Library asset identity with dedicated media-type tables and RC1 photo compatibility migration.
- Added Aperture-owned integration registry and per-capability switches.
- Added independent canonical enrichment subsystem database with typed values, namespaced labels, provenance, and lifecycle state.
- Added Settings workspaces for Library Types and Integrations.
- Added regression tests for media defaults, database separation, integration disablement, and plugin-independent enrichment retention.

## Knowledge Base 2,500-row display performance

- Replaced the per-cell `QTableWidget` projection with a model-backed `QTableView`; 2,500 rows no longer allocate 20,000 table items on the Qt event thread.
- Removed continuous `ResizeToContents` measurement from the knowledge result grid.
- Coalesced duplicate workspace activation and filter refreshes so only one SQLite reader runs at a time.
- Added visible end-to-end load timing to the Knowledge Base status line.

## Release 3 BioCLIP review action fix

- Fixed Accept so the persisted accepted state is followed by a durable success message instead of being overwritten by refresh.
- Fixed Accept All Pending & Next so every pending suggestion for the current photograph is accepted atomically before advancing.
- Fixed Accept Only & Next so the selected suggestion is accepted, other pending suggestions are rejected, and the undefined post-commit UI variable no longer raises an exception.
- Preserved deferred, previously accepted, rejected, and superseded suggestions.

## Release 3 continuous maps and portable export packages

- Added continuous raster-map composition across adjacent installed MBTiles packages.
- Added drag-to-pan geographic recentering while retaining area selection, arrow navigation, and vector-map behavior.
- Added verified export-package assembly for reports/data/previews plus selected original photos, sounds, videos, and documents.
- Added explicit continue, require-all, and exclude-original policies with manifest reporting for missing or changed originals.

## Release 3 — Reporting navigation and concurrent execution

- Added the visible top-level Reporting workspace with Export Assets, Export Data, and Generate Report tabs.
- Added File → Reporting and Export with Ctrl+E navigation.
- Connected portable packages to selected Photos/Collections assets and optional originals.
- Export package attachments and independent original-file copies now run through a bounded parallel IO pool while deterministic manifest order and atomic strict-mode behavior are retained.
- Raised the bounded Activity Center budget for independent work and added explicit concurrent budgets for export and report activities. SQLite's one-writer-per-database rule remains unchanged.

## Release 3 BioCLIP batch-navigation correction

- Fixed Accept All Pending & Next and Accept Only & Next after both actions completed their database updates but attempted to call the removed `select_public_id` UI helper.
- Batch actions now select the next visible pending suggestion through the current list-selection helper after refresh.
- Preserved the intended atomic behavior: accept all pending suggestions for the image, or accept only the selected suggestion and reject the remaining pending suggestions before advancing.

## Continuous vector map composition fix

- Corrected **All** map mode so adjacent installed vector MBTiles packages are served through one composite MapLibre tile endpoint.
- Named-area mode remains restricted to the selected package.
- Composite tile resolution uses package bounds and zoom ranges, then falls through to the next eligible package when a tile is absent.

## 3.0.0rc1.post7 — Geographic composite-map resolver

- Prevented unrelated Geofabrik regional extracts from contributing buffered low-zoom tiles to the same composite view.
- Added zoom-aware package roles: country/world overview packages remain eligible at low zoom, while regional packages enter composite mode at zoom 9 and above.
- Preserved explicit named-area viewing at each package's declared zoom range.
- Added a clear renderer message when country-level coverage is requested without an installed overview package.

## 4.0.0.dev1 Build 2 — capability adapters, sound projection and slimming

- Added a SynthesisCore BioCLIP capability adapter that preserves the existing pybioclip runtime while returning stable `CapabilityResult` taxonomy candidates.
- Added a deterministic bundled offline sound-event capability for end-to-end time-segment enrichment validation.
- Added producer-neutral renderer selection for canonical enrichment shapes and reusable review/provenance presentation models.
- Added Minimal, Standard and Research retention profiles with previewable canonical-enrichment slimming.
- Preserved accepted enrichment by default while allowing explicit cleanup of pending, rejected, expired, diagnostic, probability-vector and temporary-artifact data.

## 4.0.0.dev1 Build 3

- Added subject-centric enrichment workspace orchestration.
- Added manifest-driven parameter form generation and validation.
- Added verified offline capability/source bundle installation.
- Added secure archive extraction and source registry integration.

## 4.0.0.dev1 Build 5

- Added reusable canonical enrichment Qt components and a headless presentation controller.
- Added a desktop Enrichment Sources manager with state, result counts, deactivation, and safe removal choices.
- Preserved accepted enrichment by default during source removal.
- Added source registry listing/count APIs and Build 5 regression tests.

## 4.0.0.dev1 Build 6

- Embedded canonical enrichment in sound, video, and document subject workspaces.
- Added desktop enrichment composition, retention preview/apply orchestration, and Qt retention/bundle actions.
- Preserved explicit destructive confirmation for accepted-data removal.

## 4.0.0.dev1 Build 8
- Mirrored successful legacy BioCLIP generation into pending canonical V4 enrichment.
- Preserved the existing suggestion queue and worker execution pipeline.
- Exposed verified offline bundle installation and retention slimming in Enrichment Sources.

## 4.0.0.dev1 Build 9

- Composed the canonical enrichment controller in the main desktop window.
- Embedded canonical enrichment in Photo, Sound, Video, Document, and Observation workspaces.
- Bound Photo and Observation selection changes to stable subject identifiers.
- Added normalized renderer visualization payloads for bounding boxes, segmentation geometry, timeline events, time-frequency regions, transcript segments, and document regions.
- Added concrete Qt visualization output for spatial regions, timelines, frequency ranges, transcripts, and document page regions.
- Added Build 9 regression tests for renderer normalization and desktop subject wiring.

## 4.0.0.dev1 Build 10

- Added offline GeoJSON, GTFS, and railML reference importers.
- Added normalized spatial and transport-source translation into canonical enrichment.
- Added built-in source discovery and automatic offline source registration.
- Added desktop source-data import controls targeting observations, photos, sounds, videos, or documents.
- Added lifecycle regression tests for structured source imports and provenance preservation.

## 4.0.0.dev1 Build 11

- Added producer-neutral interactive overlay scene models with normalized hit-testing.
- Added selectable bounding-box, polygon, document-region, timeline, transcript, and time-frequency regions.
- Added a Qt canonical overlay canvas with region-selection and exact playback-time signals.
- Added playback-position synchronization for temporal canonical enrichments.
- Added Build 11 regression coverage for spatial, document, timeline, and frequency interaction.

## 4.0.0.dev1 Build 12

- Added a complete presentation contract for installed, offline, inactive, removed, missing, superseded, download-required, and update-available enrichment sources.
- Added lifecycle-aware activation/deactivation eligibility and source-state explanations.
- Added licence, attribution, and checksum visibility to the Enrichment Sources workspace.
- Added count-based source-removal previews with accepted canonical enrichment preserved by default.
- Added bidirectional audio/video synchronization hooks between canonical temporal regions and owning media players.
- Added Build 12 regression coverage for lifecycle state presentation, safe removal previews, and media playback binding contracts.

## 4.0.0.dev1 Build 13

- Integrated canonical spatial overlays into the real photo viewer.
- Added normalized image-coordinate projection for boxes and polygons that remains aligned through zoom and pan.
- Added bidirectional region selection between the photo viewer and canonical enrichment panel.
- Retained canonical overlay scenes across asynchronous preview loading and asset navigation.
- Added Build 13 regression coverage for controller composition, projection, async loading, and selection binding.

## 4.0.0.dev1 Build 14

- Added a concrete Qt audio playback widget for Sound assets using the original Aperture file instance.
- Connected canonical timeline, transcript, and time-frequency selections to exact audio seeks.
- Connected audio playhead updates back to the canonical overlay selection.
- Added producer-neutral playback position clamping and conversion outside Qt for deterministic testing.
- Added Build 14 regression coverage for path resolution and bidirectional playback synchronization.

## 4.0.0.dev1 Build 19

- Added durable source installation metadata and lifecycle audit events.
- Added missing-source verification, runtime relinking and recovery.
- Added explicit superseding links between source versions while preserving old provenance.
- Added source lifecycle refresh notifications across open media workspaces.
- Added asynchronous capability execution, progress reporting and cooperative cancellation.


## 4.0.0.dev1 Build 20

- Added source dependency activation and removal safeguards.
- Added bounded, deduplicated capability execution.
- Added queue saturation, shutdown and progress validation.
- Declared migration and backward compatibility out of scope for the clean-start release.

## 4.0.0.dev1 Build 21

- Declared the completed clean-start feature baseline as the test release candidate.
- Added deterministic manifest generation and exact package-inventory verification.
- Added consolidated release-candidate checks for assets, versions, package cleanliness and scope declarations.
- Reused exact manifest verification in deployment preflight.
- Removed generated runtime logs and other mutable artifacts from the release tree.

## 4.0.0.dev1+build26.repair19

- Added native in-application preview for Markdown and plain-text documents alongside PDF.
- Added system-application opening for Word, Excel, PowerPoint, OpenDocument, RTF, and CSV formats.
- Added clear guidance to install LibreOffice, Microsoft Office, or another compatible application when no file association is available.
- Expanded document import classification for modern and legacy office file extensions without bundling an office suite.
## 4.0.0.dev1+build28
- Added asset-centric flexible storage architecture.
- Added Managed, Linked and Hybrid import policies.
- Added storage providers, locations, health and verification history.
- Added Settings default storage policy and Tools & Resources Storage Manager.
- Added storage-aware backup scopes and linked-original manifests.
- Documented the pre-RC clean-start/no-migration policy.
- WP8 automated validation is explicitly outside this delivery.


## Build 33.3
Adds offline YOLO 11 detection/segmentation and Segment Anything ViT-B model providers.
## Fieldora 0.11.0 — Project & Work Management

- Replaced the legacy Science project planner with the `pm_*` work-management
  schema and complete project workspace.
- Added task planning, collaboration, capacity, reporting, RBAC, portals,
  templates, and multiple synchronized work views.
## Fieldora 0.11.1 — Science and Platform Navigation

- Split researcher-facing and administrator-facing navigation.
- Removed duplicated navigation destinations and introduced nested, balanced
  platform menus.
- Renamed Plants & Flowers to Plants & Fungi and aligned related screen labels.
## Fieldora 0.11.2 — Windows Installation Verification Repair

- Release Qt Science workspace resources before removing the installer
  verifier's temporary database on Windows.

## Fieldora 0.11.3 — Photo Path Search Repair

- Made text searches replace the active Latest Import view so catalog queries
  limit the visible gallery.
- Matched filename searches against both the managed path and retained original
  import path, including partial directory and basename text.
- Made search-scope changes rerun the query and allowed a newer search to
  supersede an in-progress catalog refresh.

## Fieldora 0.11.4 — Incremental Media Import

- Recognizes unchanged repeated imports across photos, RAW files, sounds,
  videos, and documents before full hashing or media probing.
- Uses a bounded head/tail fingerprint to confirm path, size, and timestamp
  matches, with automatic full-checksum fallback whenever content is ambiguous.
- Adds current-file and item-count progress during planning and execution.
- Fixes the POSIX storage-device fallback used when mount information is
  unavailable.

## Fieldora 0.11.5 — Staged Quarantine Ingestion

- Added durable, PBAC-governed multi-file submissions that remain outside the
  scientific media catalog until validation and processing.
- Added contiguous resumable quarantine uploads, immutable source-relative
  paths, checksums, contract IDs, purposes, and per-file evidence.
- Added fail-closed ClamAV integration, signature-based media detection,
  archive traversal and expansion protection, and checksum verification.
- Added leased per-file validation jobs and bounded processing fan-out of up
  to 1,000 files per job, defaulting to 250.
- Added staged-submission create, file upload, seal, status, and processing API
  routes plus operator configuration and architecture documentation.
