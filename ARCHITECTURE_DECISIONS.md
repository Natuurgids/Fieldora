# Architecture Decisions

This file records durable architectural decisions for NatureAI Next. New ideas that do not alter an approved architectural decision belong in `BACKLOG.md`.

## ADR-001 — Original photographs are immutable

**Status:** Accepted

NatureAI Next never rewrites an original photograph during normal catalog, metadata, taxonomy, or AI workflows. Human metadata, review decisions, and AI results are stored in the library catalog. Embedded-file metadata is written only by an explicit export operation to a new output.

**Consequences**

- Catalog editing is fast and reversible.
- Original evidence remains unchanged.
- Exports must make provenance and embedded-metadata behavior explicit.

## ADR-002 — Human metadata and AI evidence are separate

**Status:** Accepted

Human-confirmed catalog metadata is authoritative. BioCLIP and other AI providers create versioned suggestions and observations with model, preprocessing, prompt, provider, score, and inference provenance. AI output never silently overwrites human metadata.

**Consequences**

- Suggestions require explicit review actions.
- Re-running a newer model preserves historical evidence.
- Search may distinguish confirmed metadata from unreviewed AI suggestions.

## ADR-003 — Catalog metadata saves are optimistic and atomic

**Status:** Accepted

A single-asset edit submits the loaded asset revision together with title, caption, notes, rating, color label, pick state, and the complete user-tag set. SQLite applies the metadata and user-tag replacement in one transaction. A mismatched revision is rejected and the latest values are reloaded.

**Consequences**

- Concurrent edits cannot silently overwrite one another.
- Partial metadata/tag saves are not visible.
- Import- and plugin-sourced tag assignments are not removed by user-tag editing.

## ADR-004 — Optional capabilities own lazily activated subsystem databases

**Status:** Accepted

Aperture uses a small, durable core library database and permits optional capabilities to own separate subsystem databases. A subsystem database is created or opened only when its capability is first activated or when an existing workspace explicitly requires it. Optional data must not be added to the core database merely because a future feature may need it.

The core library database contains the minimum information required to preserve and understand the library independently: assets, file instances, imports and provenance, observations, essential observation context, confirmed taxonomy references, and stable references to optional subsystem records.

Subsystem examples include:

- `taxonomy.reference` for versioned shared taxonomy datasets;
- `maps.offline` for map-package catalogs, coverage indexes, reverse-geocoding indexes, and map caches;
- `projects.workspace` for project registration, schedules, participants, tasks, and reporting;
- `ai.knowledge` for embeddings, similarity indexes, model-specific caches, and reusable inference knowledge;
- `audit.activity` for high-volume operational history and diagnostics.

Each subsystem owns its schema, migrations, connection factory, integrity checks, lifecycle, and backup policy. Cross-database references use stable public IDs rather than database-level foreign keys. Optional subsystem failure must not prevent the core library from opening unless the user is actively entering a workflow that requires that subsystem.

Data placement follows ownership and durability, not UI convenience. For example, observation coordinates belong to the core library, while offline map tiles and package indexes belong to the map subsystem. Monitoring-site identity may remain core knowledge, while project administration belongs to the project subsystem.

**Consequences**

- Aperture avoids an ever-growing monolithic database.
- Users pay storage, migration, and maintenance costs only for capabilities they use.
- Optional subsystems may evolve and migrate independently.
- Core libraries remain portable and understandable without optional caches or services.
- Cross-database operations require explicit consistency handling because SQLite foreign keys cannot span database files reliably as an architectural contract.
- Feature design must declare database ownership before implementation.
- A missing, disabled, or corrupt optional subsystem degrades only the affected capability and must produce a recoverable, user-visible state.

**Implementation baseline (Version 2 M3.2)**

- The composition root registers optional subsystem descriptors without opening their databases.
- `maps.offline` is the first implemented subsystem and owns `maps-offline.sqlite3`.
- Activation creates and migrates the database idempotently on explicit demand.
- Subsystem health reports inactive, active, unavailable, or unhealthy without raising into core-library startup.
- Offline map packages remain managed filesystem artifacts; the subsystem database stores their catalog, coverage, checksums, status, and attribution.


### ADR-004 implementation note: offline map package lifecycle

The `maps.offline` subsystem distinguishes database health from individual package health. A healthy subsystem may contain enabled, disabled, missing, or invalid packages. Package verification is performed through renderer-independent provider contracts. Verification records observed checksums and metadata without overwriting the package's declared checksum. A package failure removes only that package from coverage queries and does not disable the map subsystem or core library.

## ADR-005 — OpenStreetMap offline support uses user-supplied local packages

**Status:** Accepted for Version 2.

Aperture's lightweight OpenStreetMap integration reads local OSM-derived raster
MBTiles packages through the optional `maps.offline` subsystem. Aperture does
not bulk-download, pre-seed, or package tiles from the public
`tile.openstreetmap.org` service. Map packages must come from a provider or
build process whose terms permit offline use and redistribution as applicable.

Every package records its data licence and attribution. The map workspace must
show attribution visibly whenever tiles are displayed. OSM-derived packages
default to `© OpenStreetMap contributors`, the OpenStreetMap copyright page,
and ODbL 1.0 unless more specific package metadata is supplied.

The core library stores coordinates and observation knowledge only. Tiles,
package catalog data, checksums, and provider metadata remain in the optional
map subsystem and shared package directory.

## ADR-006 — Temporal maps distinguish observations, inferred distribution, and confirmed movement

**Status:** Accepted for Aperture 2.0 M3.6.

A map animation must not imply that separate observations belong to one moving animal. Temporal map output is therefore classified as `observed_locations`, `inferred_distribution`, or `confirmed_movement`. Confirmed movement requires an explicitly linked observation series with subject identity, confidence, tracking method, and an approved connection policy. Authoritative time, location, identity, and series membership remain in the core library. Optional map databases may contain only rebuildable playback indexes, display caches, and preferences.

### ADR-007 — Temporal playback is a presentation over authoritative observations

**Decision:** Map timelapse playback is derived from core observation time, location, and series membership. The map subsystem and Qt workspace may cache or render frames, but they do not own authoritative movement history. Snapshot and cumulative views show observations or distribution; trail lines require an explicit observation series and retain its evidence qualification.

**Consequences:** Playback controls can evolve independently of library persistence. Missing map packages do not remove temporal knowledge, and ordinary sightings are never silently converted into confirmed movement paths.

## ADR-008 — Authoritative taxonomy reference data uses a lazy shared subsystem database

**Status:** Accepted for Aperture Version 2.

Aperture's installed taxonomy datasets, rich taxon facts, distribution records, external references, and multilingual names are shared application reference data. They therefore belong in the optional `taxonomy.reference` subsystem database rather than being duplicated into every Aperture Library.

The core library retains observation assignments, stable public taxon identifiers, user-entered taxonomy, and enough cached display information to remain understandable when the shared taxonomy subsystem is unavailable. The reference database is activated only when taxonomy browsing, installation, enrichment, or Knowledge Center reference pages are requested. Its migrations, integrity checks, replacement, and repair are independent from the library database.

Version 1 taxonomy tables remain supported during the Version 2 transition. New code must not delete or destructively migrate those records until a separately approved compatibility migration exists.

## ADR-009 — The Knowledge Center is a read-time synthesis layer

**Status:** Accepted for Aperture 2.0 M4.2.

The Knowledge Center does not own a new authoritative database. It reads shared reference taxonomy from `taxonomy.reference` and local evidence/history from the active Aperture Library, then combines them in application-layer projections using stable public identifiers. Missing optional reference data must not prevent local observations from remaining usable, and missing local mappings must not prevent reference taxon pages from being displayed. Cross-database SQL joins and copied observation totals are prohibited.

## ADR-010 — Knowledge Center navigation uses stable taxon links

**Status:** Accepted

The shared taxonomy subsystem may store an explicit mapping from an active library's local taxon public ID to a reference taxon public ID. The mapping uses the library public ID and stable public identifiers only; it does not create cross-database foreign keys or copy observation records into the reference database.

Knowledge Center pages remain read-time projections. Desktop navigation may move from a local observation history to a linked reference page and back to the authoritative local evidence timeline. Activating this workflow must lazily activate `taxonomy.reference` and must not make taxonomy availability a prerequisite for opening the core library.

## ADR-011 — Authoritative taxonomy enters Aperture as verified, attributed packages

**Status:** Accepted for Version 2.

Aperture treats BioCLIP labels as model outputs, not as the authoritative taxonomy. Shared reference taxonomy is installed through signed, versioned packages containing accepted scientific names, authorship, hierarchy, synonyms, multilingual or regional common names, distribution records, licence metadata, checksum, and attribution.

The `taxonomy.reference` subsystem owns these packages. The core library stores confirmed observations and stable links only. Model labels are mapped explicitly to reference taxon public IDs with model family, model version, mapping state, source, and timestamp. Aperture must not silently translate or invent common names.

## ADR-012 — Scientific identity is stable; common-name presentation is preference-driven

**Status:** Accepted for Version 2.

The accepted scientific name and reference taxon public ID are the stable identity. Common names are presentation metadata selected by language and region preferences. Preferences never rewrite observations, AI provenance, or installed reference records.

Authoritative taxonomy packages may be enabled or disabled without deletion. Disabled packages remain installed with licence, checksum, attribution, and provenance, but are excluded from ordinary search and Knowledge Center projections. Package lifecycle remains isolated in `taxonomy.reference`.

## ADR-015 — Asset analyses are immutable, versioned enrichment records

**Status:** Accepted for Aperture Version 2.

AI and other analysis engines enrich a specific asset. They do not add engine-specific columns to `assets` and do not overwrite prior results. Each execution creates one `asset_analyses` record linked to exactly one asset and records the engine identity, model/version, configuration hash, source content hash, timestamps, status, application version, and a lightweight result summary.

Normalized child records hold durable, meaningful enrichment such as taxon candidates and tags. Large rebuildable artifacts—including embeddings, similarity indexes, tensors, masks, and caches—remain in optional analysis subsystem databases or managed files.

Promotion from an analysis result to an authoritative observation is explicit and recorded in `analysis_observation_promotions`. The historical analysis remains unchanged. Multiple engines and model versions may enrich the same photo simultaneously.

### Consequences

- `assets` remains an evidence identity table rather than an engine-specific metadata table.
- Rerunning an engine creates a new analysis instead of replacing a prior run.
- Every promoted conclusion remains traceable to the exact analysis and candidate that supported it.
- Removing an optional AI engine does not remove lightweight enrichment already preserved in the library.
- The Knowledge Engine may consume analyses but does not execute models or rewrite analysis history.

## ADR-016 — AI suggestion generation records a parent asset analysis

**Status:** Accepted for Aperture Version 2 M5.2.

Every BioCLIP or future AI suggestion-generation execution for a photo creates an immutable `asset_analyses` parent record before inference begins. Ranked `ai_suggestions` and normalized `analysis_taxon_candidates` link to that exact execution. The existing review workflow remains the user-authority boundary and historical suggestions without a parent analysis remain valid.

Successful runs finalize the analysis with a compact result summary and ranked candidates. Failed per-photo inference finalizes the analysis as failed with an error summary; failures remain isolated from other selected photos. The inference-run record continues to describe the batch, while the asset-analysis record describes the individual photo enrichment.

## ADR-017 — Permanent asset deletion is dependency-aware

**Status:** Accepted for Aperture 2.0.

Moving an asset to Trash remains reversible and retains files, analyses, suggestions, and evidence links. Permanent deletion is a separate explicit operation. Before deletion Aperture must present a dependency preview covering managed files, derivatives, analyses, AI suggestions, queued work, observations, and analysis-to-observation promotions.

An asset that supports authoritative observations cannot be permanently deleted silently. The caller must explicitly block, unlink the asset from retained observations, or delete the related observations. Permanent deletion removes the asset row so database cascades remove asset-owned analyses, candidates, tags, suggestions, embeddings, metadata, derivatives, and file instances. A purge audit record survives with a null asset reference. Optional analysis stores must delete rebuildable records by stable asset public ID.

## ADR-018 — The Knowledge Engine is the sole cross-domain orchestrator

**Status:** Accepted for Version 2.

Workspaces and optional capabilities must not perform cross-database reasoning or attach subsystem databases for joins. The Knowledge Engine consumes high-level ports from the core library and optional capabilities, then returns immutable projections with evidence explanations. It owns no authoritative records. AI enrichment remains asset-owned data; taxonomy, maps, projects, and future modules retain their own storage boundaries. The capability registry activates optional feature services lazily and independently from subsystem database activation.

## ADR-019 — Desktop workspaces consume Knowledge Engine projections

**Status:** Accepted for Aperture Version 2 M5.6.

Cross-domain desktop views must obtain synthesized observation, taxonomy, spatial, and analysis information through the Knowledge Engine. A workspace may continue to use a capability-specific application service for data owned solely by that capability, such as offline raster tiles or taxonomy package preferences, but it must not coordinate multiple repositories itself.

Consequences:

- Knowledge Center evidence scoring and local/reference synthesis use `KnowledgeEngine` dossiers.
- Map observation overlays use `KnowledgeEngine` spatial projections; the map service continues to own tile/package access.
- Optional taxonomy and map databases remain lazy and independently owned.
- UI components render projections and do not become owners of authoritative knowledge.

## ADR-020 — Observation and AI workspaces consume Knowledge Engine context

**Status:** Accepted for Aperture Version 2 M5.7.

Observation History obtains species lists, histories, related taxa, and local observation context through the Knowledge Engine. AI Review obtains personal observation context and complete photo-enrichment history through the same boundary while retaining its single-domain suggestion review service for decisions. Workspaces must not coordinate observation and analysis repositories directly.

## ADR-021 — Workflow Engine Owns Long-Running Business Processes

**Status:** Accepted for Aperture Version 2.

Multi-step operations such as import enrichment, AI analysis, taxonomy updates, map indexing, exports, and future capability pipelines are expressed as versioned workflow definitions over Aperture's durable job system. Workspaces may start, pause, resume, or cancel workflows but must not coordinate long-running steps directly.

Each workflow step declares its job type, resource class, dependency, optionality, priority, and idempotency identity. Restarting Aperture must not require completed steps to be repeated when their durable job records already exist.

## ADR-022 — Domain Events Are the Primary Capability Integration Mechanism

**Status:** Accepted for Aperture Version 2.

Capabilities publish typed, versioned domain events for significant state changes. Subscribers are isolated: one failed subscriber must not prevent other subscribers from receiving the event or corrupt the originating transaction. Durable delivery continues to use the existing event outbox; in-process dispatch is an application boundary over those events.

Capabilities must not invoke another capability's repositories directly in reaction to state changes.

## ADR-023 — Workflow History and Derived Artifacts Have Bounded Retention

**Status:** Accepted for Aperture Version 2.

Workflow infrastructure must include cleanup from its first release. Completed jobs, dispatched events, temporary files, diagnostic bundles, and rebuildable workflow artifacts receive explicit retention policies. Active, queued, running, paused, or interrupted work is never removed by retention cleanup.

Cleanup must:

- preserve a configurable number of recent jobs per job type;
- retain failed records longer than successful records by default;
- support dry-run reporting before deletion;
- report removed record counts and reclaimed bytes;
- avoid deleting authoritative assets, observations, analyses, taxonomy, or audit evidence;
- treat optional subsystem caches according to their owning subsystem's policy.

## ADR-024 — Aperture Minimizes Runtime Technology Diversity

**Status:** Accepted for Aperture Version 2 M6.1.

Aperture is an offline-first, single-user desktop application. Workflow execution, event dispatch, scheduling, and cleanup must therefore remain embedded in the installed application and use the technologies already shipped with Aperture: Python, Qt, SQLite, the local filesystem, and in-process worker execution.

Aperture Version 2 must not require an external message broker, workflow server, cache server, database service, web service, container runtime, or independently managed daemon. Workflow steps may use only the embedded `io`, `cpu`, and `gpu` resource classes. A capability that cannot operate without an external service must remain optional and must not affect core-library availability.

New runtime technology is accepted only when it provides a clear user benefit that cannot be delivered safely with the existing stack. Rebuildable caches and indexes remain disposable, and failure of optional infrastructure must never prevent the user from opening the core library.

## ADR-025 — Cleanup is previewable, conservative, and user-visible

**Status:** Accepted for Version 2.

Aperture exposes bounded cleanup through the Maintenance Center. Cleanup must provide a non-destructive preview, estimated reclaimable storage, and a post-run report. It may remove only explicitly owned disposable data such as aged completed-job history, dispatched outbox records, stale temporary files, and empty temporary directories. It must never classify photographs, observations, accepted analysis enrichment, taxonomy packages, map packages, or unknown files as disposable.

## ADR-026 — Version 2 health and work control extend the existing Maintenance Center

**Status:** Accepted for Aperture Version 2 M6.3.

Aperture does not introduce a second health monitor, background-work controller, scheduler UI, or maintenance daemon. Version 2 subsystem checks, workflow visibility, pause, continue, stop, recovery, cleanup, backup, and restore remain owned by the existing Maintenance Center and durable job infrastructure.

The Maintenance Center may inspect the core library, optional subsystem databases, capability registration, asset-analysis relationships, and bounded workflow history. Optional subsystem inspection must not activate a subsystem database that has never been installed or used. Health inspection remains read-only by default. Existing durable job transitions remain the only supported stop/pause/continue mechanism.

### Consequences

- Version 2 capabilities register checks and job types with the established maintenance surfaces.
- No duplicate job controller or competing health score is created.
- Failed optional capabilities are reported without blocking the core library.
- Pause, continue, stop, and interrupted-work recovery use the existing SQLite job records.
- Safe repair and cleanup remain explicit user actions.

## ADR-027 — Storage and package inventory extends the existing Maintenance Center

**Decision.** Aperture exposes storage usage and installed optional-package state through the existing Maintenance Center. Inventory is read-only, scans only Aperture-owned paths, ignores symbolic links, and reads optional subsystem catalogs without activating or creating them.

**Rules.** Authoritative and rebuildable storage must be labelled separately. Package entries retain subsystem, version, enabled state, status, licence and attribution. Inventory is informational; deletion, disablement, repair and cleanup remain explicit domain-specific actions.

## ADR-028 — Platform certification is read-only and non-activating

**Status:** Accepted for Aperture Version 2 platform hardening.

Aperture certifies the approved Version 2 platform through the existing Maintenance Center. Certification verifies the core library, asset-enrichment integrity, optional subsystem registration and schema state, Knowledge Engine capability registration, and maintenance boundaries. It does not repair data, activate optional subsystem databases, install packages, or change authoritative records.

A failed optional capability is reported in its own certification section and does not make the core library unavailable. Core-library integrity and identity failures are the only certification failures that may block a release candidate. Certification results contain explicit pass, warning, or fail status and retain enough detail for user-system feedback and regression analysis.


## ADR-031 — Offline map coverage is acquired as verified regional packages

Aperture browses provider-defined geographic hierarchies and downloads only explicit, licensed, prebuilt MBTiles packages over HTTPS. Every package requires a SHA-256 checksum. Package removal reclaims basemap storage but never removes authoritative spatial records. Public OpenStreetMap tile servers are never used for bulk or offline acquisition.


### ADR: Parallel Resource Processing
Parallelize transformation stages; serialize publication.

### ADR: Adaptive Memory Workspace
Prefer in-memory processing after verified download, spilling to disk under memory pressure.

### ADR: Durable Checkpoints
Long-running resource pipelines must resume from validated checkpoints.

## ADR-032 — Street-level offline maps use replaceable vector packages

**Status:** Accepted for Build 3 implementation, subject to Windows field validation.

### Context

The Release 2 Geofabrik shapefile converter produces lightweight raster MBTiles only through zoom 10. Extending that raster pyramid to street level would multiply render time and installed storage, while downloading rendered tiles from the public OpenStreetMap service is prohibited. Aperture also must preserve offline operation, regional acquisition, attribution, and the current command-based Windows installation workflow.

### Decision

Build 3 migrates newly prepared street-level coverage toward OpenStreetMap-derived vector tiles in a single-file regional container. Acquisition, catalog, verification, and renderer remain separate ports. Existing raster MBTiles stay readable during migration.

The packaged renderer uses pinned MapLibre GL JS and PMTiles assets inside an isolated, off-the-record Qt WebEngine profile with a private archive scheme and no network tile service. Tilemaker converts regional `.osm.pbf` extracts directly to PMTiles without requiring a database server. Both remain replaceable behind existing ports and require consolidated Windows field validation.

### Consequences

* The current shapefile raster generator is maintained only for compatibility and recovery while the prototype is validated.
* Street-level acceptance requires vector generation through base zoom 14, renderer overzoom beyond 14, readable roads and labels, photo/observation overlays, pan/zoom/rotation, offline restart, bounded memory/storage, and correct attribution. Field validation rejected native zoom 16 generation after tilemaker fast-failed on Windows and warned of excessive resource demand.
* Bootstrap selects concrete renderer and converter adapters; Domain, Application, and Qt presentation do not import them.
* Downloads remain resumable, verified, atomic, and visible in Activity Center.
* Public OpenStreetMap raster or vector tile endpoints are never scraped or packaged.
* Failure of maps remains isolated from the Library and NatureAI.
* Private renderer authorities encode catalog public IDs reversibly; they never contain or resolve arbitrary filesystem paths.
* GPX tracks cross a loader port into an immutable Domain projection and are presentation overlays, not silently imported Library records.

### Alternatives considered

* **Deeper pre-rendered raster MBTiles:** rejected for the street-level target because tile counts, rendering time, and storage grow exponentially with zoom.
* **Bulk download from public OpenStreetMap tile endpoints:** rejected by provider policy and project architecture.
* **Immediate unconditional MapLibre/tilemaker bundling:** deferred until Windows packaging, licensing, resource use, and field behavior are proven.

### Build 3 implementation note — packaged runtime gate

The prototype gate treats Qt WebEngine, pinned renderer assets, and range-capable local archive access as separate prerequisites. Detection is lazy and replaceable behind a port. No vector package is advertised as renderable merely because Qt WebEngine imports or developer-supplied JavaScript assets exist. This preserves the CMD runtime model while exposing the exact next blocker for Windows field validation.

The local archive foundation resolves PMTiles by catalog public ID and serves bounded immutable ranges behind a port. It does not accept renderer-provided paths or open a localhost server. A later Qt WebEngine scheme adapter may consume this port only after its request lifecycle and browser range semantics are covered by the packaged Windows prototype.

## ADR-033 — CMD-installed Windows processes use purpose-named runtime aliases

**Status:** Accepted for Build 3.

### Context

The supported CMD installer uses a private Conda Python environment. Console/gui entry-point wrappers ultimately start `python.exe` or `pythonw.exe`, leaving users unable to distinguish Aperture, Maintenance Center, updater, and recovery processes in Task Manager. Renaming or relocating the environment's canonical Python executable would risk package and repair behavior.

### Decision

The installer copies the environment's windowless Python executable inside the same environment to purpose-named runtime aliases for Maintenance Center, updater, and recovery. The primary desktop shortcut continues to use the package-generated `Scripts\aperture.exe` GUI entry point: Windows field validation showed that a copied runtime named `Aperture.exe` did not reliably start the desktop application. Internal desktop restarts use the proven `natureai-next.exe` entry point. The canonical Python runtime remains unchanged for installation, diagnostics, and administrative commands.

NatureAI receives a separate process name only when AI execution actually crosses a process boundary. Import, thumbnails, indexing, matching, and repository enrichment remain Aperture Background Services and must not be presented as NatureAI.

### Consequences

* Install, Repair, and Uninstall retain the existing CMD entry points and Conda environment ownership.
* Repair recreates missing aliases; uninstall removes them with the environment.
* Non-Windows and missing-alias paths retain the existing Python fallback.
* The aliases change Task Manager image names but do not claim a new service, daemon, or security boundary.
* Reliable desktop startup has priority over a friendly primary process image name in the CMD-installed edition. Full primary-process branding remains gated on the packaged executable installer.


## ADR-015 — External enrichment sources own isolated databases

GBIF taxonomy and AI models are independent enrichment sources. Each source owns a replaceable database outside the operational Aperture Library. Updates build a new database in bounded transactions while the active database remains readable, validate it, and publish it through an atomic file replacement. The primary library stores observations and user assertions only; it must not be locked or migrated by enrichment-source updates. Failed or cancelled updates leave the active source unchanged, and the previous source database is retained for rollback.

## AD-0326 — Detached, replaceable taxonomy source databases

**Decision.** Building or updating a taxonomy source is an operating-system process independent of the Aperture interface. It writes only to a source-specific staging database and persistent job/checkpoint files. The active source remains read-only and available. Aperture stores only saved working-set definitions and observation-specific enrichment references; it does not copy the complete source taxonomy into the operational Library.

Taxonomy working sets are non-destructive filters over the active source, supporting cascading kingdom, class, order/subgroup, family, and rank selection.


## ADR: Offline map databases are independent resources

Each rendered region is an independent vector MBTiles SQLite database. Aperture stores only catalog metadata in its map subsystem database. Runtime tile reads open the regional database read-only; conversion, indexing, validation, and replacement occur outside the operational database. The downloaded OSM PBF remains a retained source and a replacement `.next.mbtiles` is published only after validation.

## ADR — Aperture-owned media and enrichment boundaries

**Status:** Approved

Aperture Core owns the Library, notes, collections, observations, standard media metadata, user decisions, and derivative references. Photographs, sounds, videos, and documents are first-class Library types and are enabled by default. Settings may hide or disable a type without deleting retained assets or associated information.

Canonical enrichment is stored in a dedicated Aperture-owned subsystem database. Integrations and plugins produce normalized enrichment but are not required to read, display, review, export, or retain it. Producer identifiers are provenance, not runtime dependencies. Integration databases contain only replaceable operational state, caches, checkpoints, diagnostics, and provider-specific data.

The core database maintains the integration registry and capability switches. Disabling an integration stops new processing while preserving previous enrichment and accepted observations. Each SQLite database is independently opened, migrated, and scheduled so optional work cannot block the Library interface.

> Release 3 implementation scope: no legacy-library data migration or compatibility backfill is included unless separately approved. The new structures are created for fresh Release 3 data while existing RC1 functions continue through their existing repositories.


## ADR-030 — Federated Work Execution with Unified Activity Control

**Status:** Accepted for Build 30.

Aperture keeps independent subsystem executors and persistence stores to preserve Qt responsiveness, reduce SQLite write contention, isolate failure, and permit future CPU/GPU/storage/remote placement. Every long-running subsystem implements common identity, lifecycle, progress, cancellation, retry, verification, recovery, resource-class and Activity Centre projection contracts. Unified infrastructure does not require one queue, table, database or executor.

## ADR-031 — Derivative Families Share Contracts, Not Storage Tables

**Status:** Accepted for Build 30.

Thumbnails, previews, AI features and metadata snapshots retain artifact-specific stores, workers, validation and retention. They share stable source identity, versioned processing profiles, durable state vocabulary, idempotency, failure classification and Activity Centre visibility.

## ADR-032 — Operational Health and Recovery Are Shared Contracts

**Status:** Accepted for Build 31.

Subsystems retain their own persistence, recovery algorithms and workers, but expose common health states and recover, verify and preview-cleanup operations. The Activity Centre and Maintenance Centre consume these contracts without taking ownership of execution.

## ADR-033 — Resource Coordination Does Not Centralise Execution

**Status:** Accepted for Build 31.

A lightweight Resource Broker coordinates bounded CPU, GPU, I/O, database-writer, network and memory-heavy capacity. It grants leases but never executes subsystem work. This prevents avoidable resource saturation while preserving independent queues, tables, processes and future remote hardware placement.

## ADR-034 — Operational Diagnostics Are Read-Only

**Status:** Accepted for Build 31.

Diagnostics may observe threads, activity, resource leases and subsystem health, but must not mutate authoritative state. Repair remains an explicit subsystem operation with preview and verification.

## ADR-035 — AI Review Is Multimodal and Media-Specific

**Status:** Accepted for Build 32.

Knowledge Base owns the shared review and interpretation experience for model suggestions, while enrichment execution starts from the relevant Photos, Sounds, Videos, or Documents Library. Each media review surface presents evidence appropriate to that media: image/model-input snapshots for photos, time ranges and spectrograms for sounds, clips/keyframes for videos, and page/region provenance for documents. Unsupported media providers produce no fabricated review content.

## ADR-036 — Model Activation Is Scoped by Capability

**Status:** Accepted for Build 32.

Aperture has no single global AI model. Installed models are activated only for compatible media and enrichment capabilities. Several models may be active simultaneously when their capability contracts do not conflict. Every generated suggestion stores immutable producer provenance. Review UI must distinguish the current model for new generation from the model that produced a selected historical result.

## ADR — Longitudinal specimen enrichments and dossier context (2026-08-03)

**Decision.** A specimen is a stable research subject. Encounters, identifiers, measurements,
samples and other observations are append-only, time-stamped enrichments attributed to a
user. Dossiers aggregate selected project context and may link specimens without copying or
redefining Collections.

**Consequences.** Research supports encounter histories, specimen timelines, controlled and
audited specimen merges, and explicit dossier-to-context links. Collections remain unchanged
and retain their existing purpose.
