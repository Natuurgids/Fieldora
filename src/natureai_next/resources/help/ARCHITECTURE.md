## Fieldora 0.x boundary

Fieldora is an optional local subsystem with authoritative state in
`science.sqlite3`. Projects, dossiers, artifact measurements, calendar activities,
whiteboard notes, and dossier-media references belong to Science. Library media remains
owned by `library.sqlite3`; Science stores only stable asset public IDs and never uses
cross-database foreign keys or transactions.

The intended layering is domain contracts → application services → a Science repository
→ Qt presentation. Version 0.05.1 registers Science in subsystem lifecycle, health,
integrity, inventory, and verified backup, and routes all active persistence through
an infrastructure repository with record-level diffs and revision checks. One
application-owned session is shared by every Qt Science screen. The pre-0.05 adapter
is retained as unreachable source for one field-validation comparison cycle. See
`docs/SCIENCE_ARCHITECTURE.md` and `docs/AUDIT_0.03.md`.

## Fieldora 0.06 portable project boundary

Portable project packages are explicit offline exchanges, not shared databases.
Application services select project-scoped Science records; the infrastructure codec
writes or verifies the deterministic ZIP representation. Packages never contain
original Library media in 0.06. Stable Library public IDs may be retained only after an
explicit user choice. A records checksum detects corruption, but does not represent a
cryptographic signer or institutional authorization. See
`docs/PORTABLE_PROJECT_PACKAGES.md`.

## Fieldora 0.07 PBAC boundary

Identity, role assignments, contracts, policies, and decision audit are authoritative
in the isolated `subsystems/access-control.sqlite3` database. PBAC is the overarching
model; RBAC, ABAC, contract rules, and object grants are inputs to one default-deny
decision service. Domain requests and decisions are independent of Qt and SQLite.
Desktop administration exposes the model but is not authentication or a local-machine
security boundary. Network authentication and universal server-side enforcement begin
in the server/API phase. See `docs/ACCESS_CONTROL_ARCHITECTURE.md`.

## Fieldora 0.08 governed server boundary

The first server slice is a one-node, dependency-free reference deployment. Local
credentials create expiring opaque sessions whose raw tokens are never persisted.
The versioned API authenticates every protected request and evaluates each candidate
Science object through PBAC before disclosure. The responsive web client talks only to
that API. PostgreSQL, OIDC discovery, distributed jobs, and production hardening remain
explicit adapter work. See `docs/SERVER_ARCHITECTURE.md`.

## Build 28 — Original storage policy

Build 28 introduces Flexible Storage Architecture as a distinct development milestone. Imports now offer Managed, Linked, and Hybrid original-storage policies. Users may create an Aperture-owned original, work from the source original in place, or retain both. The selected policy is remembered for future imports. Enrichments remain attached to the stable asset identity rather than a physical copy, and the inspector separately reports storage mode, availability, source file, and Aperture original. Linked imports avoid full-size duplication while retaining thumbnails, metadata, locations, and enrichments.



## Build 27 Repair 3 — Dedicated Trash Manager

- Removed **Delete permanently** from Library and Collections galleries.
- Added **Tools & Resources → Trash Manager**, a table-based maintenance workspace that avoids thumbnail decoding and gallery layout work.
- Restore and permanent deletion run in a background worker with progress reporting.
- Permanent deletion is limited to assets already in Trash and retains explicit handling for linked observations.
- The gallery remains focused on fast curation: its destructive action is now only **Trash**.

## Build 27 Repair 1

Map asset and cluster reads use canonical `locations` and `asset_locations` rows as their correctness source. The R-Tree remains an optimization elsewhere but cannot make valid located media disappear. Batch metadata updates preserve unspecified values per asset.

## Unified OpenStreetMap composition

Downloaded regional OSM vector packages remain independent storage and update units, but the map viewer exposes one logical tile source. The loopback vector server selects every package whose declared coverage intersects the requested XYZ tile, reads each vector tile independently, merges same-named Mapbox Vector Tile layers, remaps feature tag key/value indexes, and returns one combined tile. No regional package wins solely because it is first or because a buffered tile exists. The composite cache is derived and may be rebuilt without changing source packages.

Export and Reporting are separate top-level application workspaces. Export owns portable asset/data transfer; Reporting owns aggregation, templates, history, and statistics. Both share selection and permission services but have independent UI workflows.
## Release 3 output and recovery subsystems

Reporting is a top-level Aperture workspace with contextual entry points from media, observations, and collections. Export Assets, Export Data, and Generate Report share a permission-aware package builder; reports may optionally include explicitly selected original media. Backup/restore uses a central Aperture database inventory, coordinated SQLite snapshots, and capability-aware scope. Integration runtimes such as BioCLIP are excluded, while accepted normalized enrichment remains Aperture-owned data. See `docs/EXPORT_REPORTING_BACKUP_ARCHITECTURE.md`.

## Aperture V3.RC1F1 architecture baseline

NatureAI owns the integrated BioCLIP Tree-of-Life inference path. The Knowledge Base component registry exposes NatureAI/BioCLIP and GBIF independently: inference does not query GBIF as a prerequisite, while enrichment may consume NatureAI predictions afterward. Installation and Maintenance Center share one idempotent engine bootstrap and validation service.

# NatureAI Next — Architecture

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. Architectural goals

NatureAI Next uses a modular monolith with strict internal boundaries. This provides desktop deployment simplicity while preserving independently testable components and stable extension points.

The architecture prioritizes:

- complete offline operation;
- responsive desktop behavior;
- deterministic persistence;
- recoverable long-running work;
- replaceable AI backends;
- plugin extensibility;
- scalability to at least 100,000 assets without redesign;
- low coupling to PySide6, SQLite, Torch, and specific model libraries.

## 2. Architectural style

The codebase combines hexagonal architecture, domain-driven boundaries, and event-driven coordination inside one process.

### 2.1 Dependency rule

Dependencies point inward:

```text
UI / CLI / Plugins
        |
Application services and ports
        |
Domain model and policies
        ^
Infrastructure adapters: SQLite, filesystem, imaging, Torch, ONNX, update transport
```

The domain layer imports no PySide6, SQLite, Torch, ONNX Runtime, filesystem UI, or plugin implementation modules.

### 2.2 Modular monolith

The release is a single desktop product and normally one process. Internal modules communicate through explicit Python interfaces and immutable command/result objects. Separate worker processes may be used selectively for crash isolation or libraries that cannot safely share a process, but process boundaries are implementation adapters rather than application contracts.

## 3. Repository layout

```text
natureai-next/
├── PROJECT_SPEC.md
├── ARCHITECTURE.md
├── DATABASE.md
├── AI.md
├── GUI.md
├── PLUGIN_API.md
├── CONFIGURATION.md
├── ROADMAP.md
├── CODING_STANDARD.md
├── pyproject.toml
├── environment/
├── packaging/
├── resources/
├── scripts/
├── src/natureai_next/
│   ├── bootstrap/
│   ├── domain/
│   ├── application/
│   ├── ports/
│   ├── infrastructure/
│   │   ├── database/
│   │   ├── filesystem/
│   │   ├── imaging/
│   │   ├── metadata/
│   │   ├── ai/
│   │   ├── indexing/
│   │   ├── updates/
│   │   └── diagnostics/
│   ├── jobs/
│   ├── plugins/
│   ├── ui/
│   └── shared/
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    ├── migration/
    ├── performance/
    └── fixtures/
```

Package boundaries are enforced by import-lint rules and tests.

## 3.1 Modular persistence and optional capabilities

Aperture does not treat one SQLite file as the permanent home of every future feature. The core library database remains small enough to preserve and interpret assets and observations independently. Optional capabilities register lazily activated subsystem databases with the composition root.

Subsystems communicate through typed application ports and stable public IDs. They do not query one another's tables directly and do not rely on cross-file foreign keys. Each subsystem has independent migrations, integrity state, failure isolation, and backup or rebuild policy. A missing optional subsystem must not prevent the core library from opening.

The architecture decision and mandatory implementation rules are defined in `ARCHITECTURE_DECISIONS.md` ADR-004 and `CODING_STANDARD.md` section 10.1.

## 4. Major modules

### 4.1 `bootstrap`

The composition root:

- resolves application and library paths;
- loads configuration;
- initializes logging and diagnostics;
- opens and validates a library;
- runs database migrations;
- discovers compatible plugins;
- creates infrastructure adapters;
- wires application services;
- starts job schedulers;
- launches the PySide6 shell.

No other module constructs the complete object graph.

### 4.2 `domain`

Contains business concepts and policies:

- asset and file identity;
- observation and taxonomy references;
- user metadata precedence;
- collection membership;
- import conflict decisions;
- job state rules;
- suggestion review states;
- value objects for hashes, coordinates, timestamps, confidence scores, and regions.

Domain objects do not perform persistence or UI work.

### 4.3 `application`

Contains use cases and orchestration:

- import planning and execution;
- metadata editing;
- search;
- collection management;
- taxonomy update application;
- AI analysis submission and review;
- export;
- backup and validation;
- settings changes;
- plugin command registration.

Each use case has typed input and output models. Application services own transaction boundaries through a unit-of-work port.

### 4.4 `ports`

Defines Protocols or abstract interfaces for:

- repositories and unit of work;
- file storage and hashing;
- metadata readers;
- image decoders and thumbnail renderers;
- search and vector indexes;
- model registry and inference engines;
- taxonomy package source;
- update transport;
- clock, UUID generation, and diagnostics;
- UI-facing task dispatch.

Ports are stable contracts. Infrastructure and plugins implement ports.

### 4.5 `infrastructure`

Adapters for external technologies:

- SQLite repositories and migrations;
- Windows and portable filesystem handling;
- ExifTool or library-based metadata extraction adapter;
- image decoding and thumbnail generation;
- Torch/CUDA and ONNX inference;
- persisted vector index;
- package download and signature validation;
- structured logging and crash reports.

### 4.6 `jobs`

Persistent background execution framework:

- durable job records;
- bounded worker pools;
- resource classes;
- cancellation tokens;
- progress snapshots;
- retry policy;
- startup recovery;
- dependency chains;
- user notifications.

### 4.7 `plugins`

Plugin discovery, validation, capability registration, lifecycle, and fault containment. The core does not import plugin packages directly.

### 4.8 `ui`

PySide6 presentation layer:

- application shell;
- workspaces;
- models and view models;
- dialogs and panels;
- command routing;
- selection and navigation state;
- UI-specific formatting.

Widgets never issue SQL or call Torch directly.

### 4.9 `shared`

Small dependency-free utilities used by multiple inner modules, such as result types, immutable pagination tokens, error identifiers, and serialization helpers. It must not become a miscellaneous dumping ground.

## 5. Runtime topology

### 5.1 Main process

The main process owns:

- Qt event loop;
- application service graph;
- database connection factory;
- job scheduler;
- plugin manager;
- UI state.

### 5.2 Worker execution

Three execution classes are defined:

1. **I/O workers** for scanning, hashing, file copies, metadata extraction, and export.
2. **CPU workers** for image decoding, thumbnail generation, and CPU-bound transforms.
3. **AI worker** for serialized or carefully batched access to GPU models.

The scheduler prevents unbounded concurrency. Default limits are configuration-driven and hardware-aware.

### Staged multi-user ingestion

Untrusted multi-user delivery terminates in quarantine rather than the governed
media catalog. Durable submission and per-file records preserve organization,
project, contract, purpose, relative path, checksum, and validation evidence.
Sealing creates independently leased validation jobs; accepted files then fan
out into bounded processing batches. Malware, integrity, media-signature, and
archive-safety failures remain quarantined and cannot be resolved through
normal media routes. See `STAGED_INGESTION.md`.

A process-based worker adapter may be used for unsafe native libraries or memory isolation. It must communicate using versioned messages and may not access UI objects.

### 5.3 Database access

- Connections are never shared across threads.
- Reads may occur concurrently using separate read connections in WAL mode.
- Writes are serialized through short transactions controlled by application services and the job framework.
- Database callbacks never update widgets directly; results return through queued Qt signals or the UI dispatcher.

## 6. Application communication

### 6.1 Commands and queries

User actions become application commands or queries. Examples:

- `ImportFilesCommand`
- `UpdateAssetMetadataCommand`
- `SubmitAnalysisJobCommand`
- `ReviewSuggestionsCommand`
- `SearchAssetsQuery`

Command objects are immutable and validation occurs at the boundary.

### 6.2 Domain events

Domain events represent committed facts, such as:

- `AssetsImported`
- `AssetMetadataChanged`
- `SuggestionsReviewed`
- `TaxonomyActivated`
- `ModelInstalled`

Events are written to an outbox table in the same transaction as state changes. An in-process dispatcher consumes the outbox to invalidate caches, update indexes, refresh views, and invoke plugin subscribers. Handlers must be idempotent.

The outbox is not intended as an external event-sourcing system. Current relational state remains authoritative.

### 6.3 Error model

Expected failures use typed application errors with stable codes and user-safe messages. Unexpected exceptions are logged with correlation identifiers and converted at boundaries.

Errors carry:

- stable error code;
- human-readable summary;
- optional technical detail for logs;
- retryability;
- affected entity identifiers;
- remediation action where known.

## 7. Library layout

A library directory contains:

```text
My NatureAI Library/
├── library.sqlite3
├── originals/            # only when managed storage is used
├── sidecars/             # optional application-owned sidecars
├── derivatives/
│   ├── thumbnails/
│   └── previews/
├── indexes/
│   ├── vectors/
│   └── search/
├── models/               # optional library-pinned models
├── taxonomy/
├── backups/
├── logs/
└── library.json
```

`library.json` contains non-secret bootstrap metadata such as library UUID and minimum application compatibility. It is not a substitute for relational metadata.

Global application data, downloaded shared models, global plugins, and user preferences reside outside the library as defined in `CONFIGURATION.md`.

## 8. Storage modes

### 8.1 Managed originals

Files are copied or moved into a content-organized library directory. The database records the original import path and current managed path.

### 8.2 Linked originals

Files remain at user-controlled paths. NatureAI tracks identity and availability. Linked folders may be offline or moved, and relinking is supported.

### 8.3 Hybrid libraries

Managed and linked assets may coexist. Storage mode is a property of each file instance, not a library-wide irreversible choice.

## 9. Job architecture

### 9.1 Job states

`queued`, `blocked`, `running`, `pausing`, `paused`, `cancelling`, `cancelled`, `succeeded`, `failed`, `interrupted`.

State transitions are validated centrally.

### 9.2 Job requirements

Each job type defines:

- versioned payload schema;
- resource class;
- idempotency key strategy;
- progress model;
- retry policy;
- cancellation checkpoints;
- recovery behavior;
- cleanup behavior;
- result schema.

### 9.3 Resource coordination

The scheduler controls:

- maximum I/O concurrency;
- maximum CPU concurrency;
- one active model-loading/inference coordinator per GPU device by default;
- VRAM budget;
- foreground versus background priority;
- pause-on-battery behavior if enabled.

## 10. Caching

Caches include:

- thumbnails and previews;
- decoded image memory cache;
- query result pages;
- taxonomy lookup cache;
- loaded model cache;
- vector search index.

All caches have:

- explicit ownership;
- bounded size;
- versioned keys;
- deterministic invalidation;
- rebuild behavior.

No cache is the sole copy of user data.

## 11. Update architecture

Three independent update channels exist:

1. application updates;
2. model packages;
3. taxonomy packages.

Update workflows are explicit user actions or configured checks. Packages are downloaded to staging, verified, then atomically activated. Failed activation leaves the prior version intact.

The network adapter is inaccessible to ordinary application services. Only update services receive it through dependency injection.

## 12. Plugin integration

Plugins register capabilities through `PLUGIN_API.md`. Core extension points include:

- metadata readers;
- import validators;
- AI model providers;
- taxonomy providers;
- exporters;
- commands and panels;
- background job types;
- event subscribers.

Plugins cannot replace core transaction management, database migration ownership, security policy, or original-file immutability.

## 13. Observability

Offline observability includes:

- structured rotating logs;
- job history;
- performance counters;
- database integrity reports;
- model and provider diagnostics;
- optional local diagnostic bundle export.

No telemetry is transmitted automatically.

## 14. Testing architecture

- Unit tests target domain policies and application services using in-memory fakes.
- Contract tests ensure every adapter and plugin implementation satisfies its port.
- Migration tests upgrade representative historical databases.
- Integration tests use temporary filesystem libraries and real SQLite.
- GUI tests cover view models and selected Qt workflows.
- Performance tests use synthetic 10k, 100k, and 1M metadata catalogs.
- AI regression tests use a versioned local image fixture set and tolerance-based outputs.

Full end-to-end integration testing is intentionally concentrated late in the roadmap, but compilation, static checks, unit tests, contract tests, and focused integration tests run continuously.

## 15. Architectural decisions

### AD-001: Modular monolith

Chosen over microservices because offline desktop deployment, transactions, packaging, and debugging are simpler. Internal boundaries preserve future extraction options.

### AD-002: SQLite authority

SQLite is the authoritative metadata store. External indexes and derivatives are rebuildable caches.

### AD-003: Persistent job system

Long-running work is represented durably to support cancellation, recovery, and predictable UI behavior.

### AD-004: In-process plugins with trust warning

Initial plugins run in-process for capability and performance. Compatibility validation and fault isolation are mandatory; security sandboxing is not claimed.

### AD-005: Outbox-based internal events

Events are persisted atomically with state changes to prevent missed cache/index updates after crashes.

### AD-006: Application-layer transaction ownership

Use cases own transaction boundaries. Repositories do not commit independently.

### Lightweight offline map presentation

The Qt map workspace depends on an application-level map-workspace service rather than opening MBTiles or library databases directly. The service combines local tile retrieval from the lazily activated `maps.offline` subsystem with bounding-box projections from the core library. The renderer is intentionally replaceable: map math, package resolution, attribution, and spatial retrieval remain outside Qt painting code.

### Street-level offline map evolution

The existing raster MBTiles provider remains a compatibility adapter, not the long-term street-level engine. Pre-rendering every raster tile to street zoom produces an unacceptable storage and conversion multiplier. Build 3 therefore standardizes the next map packages on vector tiles in a single-file regional container, behind the existing map provider and workspace ports.

Bootstrap owns renderer and converter selection. The Qt workspace consumes map-view projections and never opens a vector archive or starts a conversion executable directly. Acquisition continues to own HTTPS retrieval, provider verification, resumable partial files, atomic publication, package registration, licensing, and attribution. A renderer failure cannot prevent the Library from opening.

MapLibre GL JS with the PMTiles browser adapter is the isolated renderer prototype. Tilemaker 3.0.0 is the packaged Windows conversion adapter: Bootstrap constructs it from a pinned tool manifest and Infrastructure verifies its executable hash before every run. Infrastructure drains converter output to a temporary file instead of an unread pipe, bounds surfaced diagnostics, owns cancellation escalation, and removes partial output. Following field validation, tilemaker generates through standard vector base zoom 14 and MapLibre overzooms the vector data for street-level interaction. The packaged prototype still requires field validation of readable street detail, labels, rotation, overlays, bounded resource use, and clean offline startup before commercial release.

Map acquisition owns storage admission before download and conversion. When a provider catalog omits extract sizes, Application exposes a conservative per-region reserve to the setup workflow. Once the provider response supplies a content length, acquisition recalculates the remaining source, staged vector output, and conversion headroom before writing the bulk response body. This guard remains within the Maps workflow and does not introduce a general resource scheduler ahead of the NatureAI Foundation build.

Map conversion concurrency remains governed by the existing capacity-aware background processing system. The converter adapter owns one process invocation, verification, cancellation, diagnostics, and cleanup but does not impose a global concurrency policy. Field validation superseded the temporary single-conversion assumption from Builds 3.262–3.270.

The renderer receives no catalog path or raw public ID. Bootstrap installs one private scheme handler; the UI converts each public ID into a canonical Base32 authority and the handler reverses it before calling the catalog-authorized archive service. This supports provider IDs containing punctuation without exposing filesystem paths or opening a localhost service.

MapLibre viewport changes return through a narrow presentation callback containing latitude, longitude, and zoom. Application recalculates bounded spatial projections and the UI publishes local GeoJSON for photographs, observations, monitoring sites, temporal movement, and GPX tracks. GPX parsing remains an Infrastructure adapter behind a port; Qt only selects a file and presents the resulting Domain track. No overlay changes ownership of Library data.

Map renderer readiness crosses the architecture as a Domain projection through the map-workspace port. Infrastructure reports which installed adapter can render each package; Application exposes that result without selecting a concrete renderer; Qt presents readiness and only requests tiles from packages declared displayable. A valid but unsupported vector package therefore remains managed data rather than becoming a rendering exception.

The packaged renderer gate is evaluated in three stages: Qt WebEngine must load, approved pinned MapLibre/PMTiles assets must exist, and an Aperture-owned local range-capable archive bridge must be available. Infrastructure performs this lazy probe through a replaceable port. An installed module or asset alone never causes a vector package to be advertised as renderable.

The archive-access foundation accepts a catalog public ID plus a bounded offset and length. Infrastructure resolves the installed PMTiles path, verifies package state and observed size, and returns an immutable Domain slice. Renderer input cannot select an arbitrary filesystem path. The port is transport-neutral so a later Qt WebEngine scheme adapter can implement browser range semantics without moving file ownership into UI or opening a network listener.

Browser range semantics are translated in Application. Only one explicit bounded `bytes=start-end` request is accepted; ambiguous or potentially unbounded forms are rejected before the archive port is called. The response projection carries partial-content metadata without importing HTTP, Qt, or a renderer library. The eventual Qt scheme adapter is limited to request/response translation around this service.

Qt WebEngine access uses a private `aperture-map://<package-id>/archive` scheme rather than a localhost server. Its adapter is imported lazily, accepts only GET with a bounded range, and parents each reply buffer to the request job. Scheme registration and profile installation remain Bootstrap responsibilities and do not make the renderer ready without approved assets.

Bootstrap registers the private scheme before constructing the Qt desktop application. Import, binary-load, or registration failures are recorded as optional renderer unavailability and do not interrupt Library startup. Registration alone does not construct a WebEngine profile or activate vector rendering.

Renderer assets are executable release inputs and cross a cryptographic trust gate. An approved manifest must list exactly the required MapLibre JavaScript/CSS and PMTiles JavaScript with pinned versions, licence identifiers, and SHA-256 hashes. Filename presence alone is never renderer readiness.

## Build 1 boundary enforcement

The Foundation build enforces four executable import contracts:

* Domain is independent.
* Ports do not depend on outer layers.
* Application does not import Infrastructure or Bootstrap adapters.
* UI does not import Infrastructure, directly or transitively.

All four contracts pass at the field-validated Build 1.29 Foundation freeze. Bootstrap owns concrete adapter selection, including Library lifecycle and Maintenance Center platform operations.

## Build 2 import-source policy

Import source classification is a Domain policy. Infrastructure performs filesystem traversal and uses that policy to avoid treating recognized metadata sidecars as standalone photographs. Application Import Service owns immutable planning, cryptographic duplicate decisions, RAW fallback reporting, and transaction orchestration. Concrete decoders and metadata readers remain replaceable ports selected by Bootstrap.

Camera RAW decoding is an Infrastructure adapter over LibRaw/rawpy selected by Bootstrap through the existing image-decoder and metadata-reader ports. Rendered formats remain on Pillow. Catalog thumbnails/previews use an injected RAW renderer but retain one cache contract. No RAW dependency enters Domain, Application, Ports, or Qt, and an unsupported camera variant fails one import item rather than the plan.

XMP companion discovery is an injected import port. The filesystem adapter performs bounded, non-recursive discovery; Import Service owns association and provenance. Linked imports retain external sidecars, while managed and hybrid imports use a separately composed Library sidecar store. Source removal occurs only after verified placement and transaction commit.

XMP interpretation uses the existing metadata-reader port with a dedicated Infrastructure adapter. Parsing is read-only, size/value bounded, and rejects document types/entities. Import Service applies descriptive fields only through existing catalog transaction ownership, stores import keywords separately from user tags, and records a normalized checksummed snapshot against the sidecar file. Parse failure is isolated from photo import.

## Build 2 batch review transactions

Batch ratings, color labels, and pick/reject flags enter through an Application service and a stable catalog-edit port. The Application layer validates and bounds the command. The SQLite adapter verifies every selected public ID and optimistic revision before updating any asset, then commits the complete batch in one transaction. Presentation code must use this boundary rather than issue per-photo edits that could leave partial state.

The review patch carries explicit update flags so presentation can distinguish an unchanged field from a deliberate clear. Library stores the displayed optimistic revision with each grid item, submits the complete selection through a background worker, and refreshes after completion or conflict. Qt does not own transaction behavior.

## Build 2 metadata search

Camera maker, camera model, and lens are versioned Domain query fields. Application converts user-facing filters into the same structured representation used by saved searches and smart collections. Infrastructure compiles them against normalized image properties using parameterized, escaped, case-insensitive matching. Qt owns only filter controls and continues to execute search through the existing background service boundary.

GPS bounds extend the user-facing filter value without adding a new spatial subsystem. Application requires a complete legal south/north/west/east box and emits the existing latitude/longitude predicates. Infrastructure applies the parameterized bounds to capture locations already stored in the Library. Qt owns opt-in coordinate controls only; map rendering and online services are unaffected.

Exact-duplicate visibility is a read-only structured-query capability. Infrastructure evaluates cryptographic SHA-256 equality across available file instances; missing files and null hashes are excluded. Presentation exposes only a filter. Merge, removal, ignore decisions, history, and perceptual similarity require separate approved workflows and are not inferred from hash visibility.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.

## Continuous map canvas

Raster map files remain independent storage units, but `OfflineMapWorkspaceService` resolves every visible tile against all enabled, renderable packages that support the active zoom. Geographic coverage, not the package selected at startup, determines which adjacent package supplies a tile. The Qt canvas keeps a prefetched five-by-five tile window and recenters after drag navigation. Existing single-package selection remains a centering and management action rather than a rendering boundary.

## Portable export packages

`ExportPackagePlan` and `LocalExportPackageBuilder` assemble report/data attachments and optional original media in one verified, atomic directory. Each original has an Aperture asset identity and media type. Missing and checksum-mismatched originals are represented in `manifest.json`; the selected policy either continues, requires all originals, or excludes originals. Integration runtimes and caches are not package inputs.

## Concurrent desktop execution

Independent Activity Center operations use bounded concurrency derived from available logical CPUs. Export-data, export-package, report-generation, and offline-map preparation activities have explicit independent budgets. Portable package attachments and original files are copied concurrently to unique staging paths. This does not relax database safety: each Aperture-owned SQLite database still has one serialized writer queue and many read-only connections.

### Zoom-aware composite map source resolution

The continuous map resolver separates storage availability from geographic ownership. In All mode, country/world overview packages may serve low zooms. Regional packages are eligible from zoom 9 onward and only inside their declared geographic envelope. Tile existence alone never grants geographic ownership because regional MBTiles may contain buffered low-zoom context outside the named region. Named-area mode bypasses the composite threshold and retains the package's declared zoom range.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.


## Repair 17 Photos gallery virtualization

The Photos workspace uses a fixed-grid `QListView` backed by a lightweight `QAbstractListModel` and painted by a `QStyledItemDelegate`. Paging appends model rows in one insertion transaction. Thumbnail decoding is restricted to the viewport and a small prefetch margin, with identity-based job deduplication. This keeps layout and image work proportional to visible content rather than total loaded assets.


## Repair 18 gallery mutation and paging

Trash and permanent-delete completion mutate the existing gallery model with targeted row-removal signals rather than resetting or replacing the model. This preserves the view, paging cursor, and loaded pages. The vertical scrollbar now invokes a guarded near-bottom paging check; a deferred check after insertion or removal also fills an underfilled viewport without duplicate page requests. Thumbnail state is pruned only for removed public IDs.

## External document application boundary (Repair 19)

Aperture owns document cataloging and native display of PDF, Markdown, and text. Word-processing, spreadsheet, presentation, RTF, CSV, and OpenDocument rendering remains an operating-system integration boundary. The Qt UI delegates those formats through the platform URL/file-association service and does not bundle an office runtime.

## Build 27 desktop shell and shutdown reporting

Build 27 changes presentation-level navigation only; existing workspace identifiers remain stable. The main window reports the existing graceful shutdown sequence through a modal progress dialog, including active-work checks, required backup creation, worker termination, session-state persistence, and final resource release.


## Build 27 Repair 4 vector overlay lifecycle

The Qt vector-map adapter owns the latest serialized overlay payload independently of the transient WebEngine JavaScript context. Overlay updates that arrive before document navigation completes are retained and replayed from `loadFinished`, with bounded delayed retries for asynchronous MapLibre style construction. The document exposes one idempotent foreground-restoration operation that recreates missing GeoJSON sources and layers, forces visibility, moves the Aperture stack above the basemap, and reapplies the latest data after style and package lifecycle events. A style reload can therefore discard renderer objects without discarding Application-owned map projections.

## Build 28 storage boundary

Assets are catalog identities. Original media locations are represented by storage providers and storage locations. Metadata, locations, observations, collections, AI outputs and user enrichments reference the asset, never a filesystem path. A source location and an Aperture master may coexist. Availability and verification are properties of each storage location. Destructive removal of a managed copy is blocked unless another source remains.

## Build 32 multimodal Knowledge Review

Knowledge Base provides the common review control plane for AI-derived suggestions. Execution remains federated by media capability and begins in the relevant Library workspace. The review hub exposes Overview, Photos, Sounds, Videos, Documents, Comparisons, and Accepted Knowledge. Media-specific evidence renderers remain independent and replaceable.

Model activation is capability-scoped. The system may keep photo, sound, video, and document models active simultaneously. Suggestion provenance always identifies the exact producing model and is never inferred from the currently active generation assignment.
## Offline Excalidraw document boundary

The active Science whiteboard route is a document workflow. Standard
`.excalidraw` files are stored in `Documents/Whiteboards`; immutable snapshots
and their checksum metadata are stored in `Documents/Whiteboards/.versions`.
Fieldora embeds the complete Excalidraw React application in a dedicated Qt
WebEngine profile. JavaScript, styles, fonts, locales, and diagram modules are
packaged locally. A URL interceptor permits only `file`, `qrc`, `data`, and
`blob` schemes, while the page content-security policy disables connections,
frames, and external objects. A Qt WebChannel bridge loads and atomically
autosaves the active Documents file. Fieldora never sends a whiteboard to a
hosted editor.

The pre-0.09.7 `science_whiteboards`, `science_whiteboard_elements`, and
`science_dossier_whiteboards` structures are inactive compatibility data. They
are neither migrated nor deleted. New dossier relations use ordinary stable
Document links.
