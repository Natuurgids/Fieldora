## Release 3 approved export and recovery requirement

Aperture shall provide permission-aware Asset Export, Data Export, and Reporting. Reports may aggregate observations down to a total count and may optionally include explicitly selected original photos, sounds, videos, and documents. Missing originals are represented in the package manifest according to the selected strict/continue policy. Backup and restore shall include the chosen set of Aperture-owned subsystem databases rather than only the library database, default to complete-library recovery, support explicit active-type/custom scopes, and exclude integration runtimes such as BioCLIP while retaining accepted normalized enrichment.

## Aperture V3.RC1F1 release requirement

The standard NatureAI installation shall provide an immediately activatable BioCLIP Tree-of-Life classifier without requiring GBIF or a user-supplied CSV. Installation, repair, and offline import shall converge on the same validated engine state.

# NatureAI Next — Project Specification

**Status:** Approved design baseline  
**Document version:** 0.2  
**Applies to:** Entire NatureAI Next repository  
**Last updated:** 2026-07-13

## 1. Purpose

NatureAI Next is a new, commercial-quality, completely offline wildlife photo management application for Windows. It manages large personal and professional natural-history image libraries, supports local AI-assisted discovery and identification, and preserves user control over metadata and taxonomy.

NatureAI Legacy 1.0 is feature-frozen and may be consulted only as a behavioral reference. NatureAI Next must not import, modify, extend, or depend on Legacy code.

**Implementation status:** Milestones 1–7 are implemented. The approved architecture remains unchanged.

The nine root design documents are the repository's single source of truth:

- `PROJECT_SPEC.md`
- `ARCHITECTURE.md`
- `DATABASE.md`
- `AI.md`
- `GUI.md`
- `PLUGIN_API.md`
- `CONFIGURATION.md`
- `ROADMAP.md`
- `CODING_STANDARD.md`

Implementation may begin only after these documents are approved. A code change that introduces or changes an architectural decision must update the relevant design document first.

## 2. Product mission

Build the best fully offline wildlife photo management application for Windows, optimized for a serious collection of 10,000 photographs initially and 100,000 or more over time.

The application must remain useful without an internet connection after installation. Internet access is permitted only for:

1. downloading AI models;
2. downloading taxonomy updates;
3. downloading software updates.

No cloud storage, telemetry upload, cloud AI, cloud inference, remote metadata processing, or mandatory account may be used.

## 3. Supported environment

### 3.1 Primary platform

- Windows 11 Pro, 64-bit
- Python 3.11
- Miniconda development environment
- NVIDIA RTX 4070 Laptop GPU with 8 GB VRAM
- Intel Core Ultra 9 with NPU
- 64 GB RAM
- 2 TB SSD
- Docker Desktop for development services and reproducible tooling only; the released desktop application must not require Docker.

### 3.2 Runtime acceleration

- NVIDIA CUDA is the preferred inference accelerator.
- CPU inference is mandatory as a safe fallback.
- ONNX Runtime may be used when it materially improves startup time, portability, or performance without reducing output fidelity.
- Intel NPU support is optional until a stable, tested provider is available. The architecture must permit a future execution provider without changing application-layer contracts.

## 4. Users and principal workflows

### 4.1 Intended users

- wildlife photographers;
- naturalists and field recorders;
- biodiversity researchers managing personal image sets;
- users maintaining multi-country collections;
- advanced hobbyists who require local ownership and privacy.

### 4.2 Core workflows

1. Import files from folders, memory cards, and existing managed libraries.
2. Detect duplicates and preserve all original files without destructive modification.
3. Browse a responsive thumbnail grid and inspect full-resolution images.
4. Edit ratings, labels, tags, locations, dates, notes, and taxonomy.
5. Run local AI analysis to generate embeddings, broad organism groups, candidate taxa, and visual similarity results.
6. Review AI suggestions and accept, reject, or defer them in batches.
7. Search by text, structured metadata, taxonomy, location, date, and visual similarity.
8. Organize images into dynamic searches and explicit collections.
9. Export selected originals, derivatives, and metadata without requiring NatureAI Next.
10. Back up and restore the library using documented, verifiable procedures.

## 5. Biological and geographic scope

### 5.1 Subject scope

The data model must support, without schema redesign:

- trees;
- flowers and other vascular plants;
- birds;
- butterflies and moths;
- dragonflies and damselflies;
- other insects and arthropods;
- fungi and mushrooms;
- mosses and liverworts;
- lichens;
- mammals;
- habitats;
- landscapes;
- additional organism groups introduced by taxonomy updates or plugins.

### 5.2 Geographic scope

Primary use is in the Netherlands and Bulgaria, with Europe as the initial broader region and worldwide expansion expected. Geographic modeling must not hard-code countries or taxonomic regions.

## 6. Product boundaries

### 6.1 In scope

- managed and linked photo libraries;
- common still-image formats supported by the selected imaging stack;
- embedded and sidecar metadata reading;
- non-destructive application metadata;
- local taxonomy database and versioned updates;
- local AI inference and similarity search;
- local background processing;
- plugin extensions;
- offline update packages;
- import, export, backup, and recovery;
- accessibility, keyboard operation, and high-DPI support.

### 6.2 Out of scope for the first stable release

- cloud synchronization;
- multi-user concurrent editing over a network share;
- mobile applications;
- web-hosted user interface;
- video asset management;
- RAW development comparable to a dedicated photo editor;
- destructive pixel editing;
- automatic publication to third-party services;
- authoritative scientific validation of AI identifications.

The architecture may permit these capabilities later, but their future possibility must not complicate or destabilize the first release.

## 7. Functional requirements

### 7.1 Library management

- A library is a self-contained logical catalog with one SQLite database and associated managed data directories.
- Multiple libraries may exist, but only one library is writable in a single application process.
- Import supports copying into managed storage, moving into managed storage, and referencing files in place.
- Originals are immutable from the application's perspective. Rotation, crops, edits, and annotations are stored as metadata or derivatives.
- Files are identified by content hash and normalized file identity; duplicate policy is configurable per import.
- Missing linked files are tracked and relinkable.
- External changes are detected by scheduled or user-triggered reconciliation.

### 7.2 Metadata

- Preserve original embedded metadata.
- Store normalized capture time with source, timezone certainty, and user override history.
- Support GPS coordinates, country, administrative region, locality, and free-form place notes.
- Support rating, color label, pick/reject state, title, caption, notes, copyright, creator, and custom tags.
- Support multiple organism observations per image and non-organism scene classifications such as habitat or landscape.
- Keep AI-generated values separate from user-confirmed values.
- All material metadata changes must be auditable.

### 7.3 Taxonomy

- Use a versioned local taxonomy store.
- Represent accepted names, synonyms, vernacular names, ranks, parent-child relationships, identifiers, and geographic relevance.
- Permit multiple taxonomy sources while retaining source provenance.
- Allow user-defined taxa or provisional labels without corrupting imported source taxonomies.
- Taxonomy updates must be transactional and reversible by restoring the preceding package.

### 7.4 Search and organization

- Structured search must combine metadata predicates using AND, OR, and NOT.
- Full-text search must cover user-visible textual metadata, tags, common names, and scientific names.
- Saved searches store a versioned query representation, not raw SQL.
- Collections may be manual or smart.
- Similarity search must be local and tied to a selected embedding model version.
- Search results must be deterministic for equal scores through stable secondary ordering.

### 7.5 AI assistance

- BioCLIP is the initial vision-language foundation model.
- AI functions include embeddings, zero-shot classification, candidate ranking, broad biological grouping, duplicate/near-duplicate assistance, and similarity search.
- Every inference output records model, model version, preprocessing version, execution provider, parameters, and timestamp.
- AI suggestions never silently overwrite user-confirmed metadata.
- Confidence values must not be presented as calibrated probabilities unless a calibration process is explicitly documented and model-specific.

### 7.6 Import and export

- Import is resumable and idempotent.
- Import failures are isolated per file and do not invalidate successful items.
- Export supports originals, selected derivatives, JSON/CSV metadata, and standards-based sidecars where feasible.
- Export naming templates are validated before execution.
- Export never changes the source library.

### 7.7 Reliability and recovery

- Long-running work uses persistent background jobs.
- Application termination must not corrupt the database or leave an unrecoverable half-imported library.
- Startup recovery marks interrupted jobs and resumes or rolls them back according to job type.
- Derived artifacts, thumbnails, and vector indexes are rebuildable.
- The SQLite database and originals are authoritative; caches are not.

## 8. Non-functional requirements

### 8.1 Performance targets

Targets apply on the stated reference hardware with a local SSD:

- cold start to usable library shell: target under 5 seconds for 100,000 assets, excluding optional model loading;
- first library page visible: target under 2 seconds after database open;
- scrolling: visually smooth at 60 Hz where GPU/UI conditions permit, with no synchronous disk or inference work on the UI thread;
- metadata search: target under 300 ms for common indexed queries at 100,000 assets;
- full-text search: target under 500 ms for common terms at 100,000 assets;
- thumbnail cache hit: target under 50 ms per visible item at the storage layer;
- import discovery: at least 1,000 filesystem entries per second under typical SSD conditions, independent of hashing and metadata extraction;
- batch AI throughput: maximize GPU utilization while remaining within configurable VRAM limits and preserving UI responsiveness.

These are engineering targets, not release claims, until measured by repeatable benchmarks.

### 8.2 Scalability

- The relational schema must support at least 1,000,000 asset rows without redesign.
- Pagination uses keyset pagination for large result sets; unbounded `OFFSET` is prohibited in performance-critical paths.
- Bulk operations use bounded batches and explicit transaction scopes.
- Large binary files are not stored in SQLite.

### 8.3 Security and privacy

- No user content leaves the machine unless the user explicitly exports it.
- Network access is disabled by default at the application service layer and only update services may request it.
- Downloaded artifacts require integrity verification and, for first-party packages, signature verification.
- Plugins run in-process initially and are therefore trusted code; installation must communicate this clearly.
- Secrets are not expected for ordinary operation. Any future credentials must use Windows Credential Manager, not plaintext configuration.

### 8.4 Accessibility and localization

- Keyboard navigation is required for primary workflows.
- All actionable controls require accessible names and focus states.
- Text must remain usable with Windows scaling up to at least 200%.
- UI strings are externalized from the beginning.
- English is the initial interface language; the architecture supports translations.
- Taxon common names are locale-sensitive and separate from interface localization.

### 8.5 Maintainability

- Stable service and plugin contracts.
- Typed Python throughout production code.
- Explicit dependency direction.
- Database migrations are forward-only in production, with backups for downgrade recovery.
- No global mutable application state outside controlled composition roots.
- No hidden network calls.

## 9. Canonical terminology

- **Asset:** A logical catalog item representing one photographic work.
- **File instance:** A concrete file path containing an original or derivative associated with an asset.
- **Original:** An imported source file treated as immutable.
- **Derivative:** A generated preview, thumbnail, export rendering, or other rebuildable representation.
- **Observation:** A subject occurrence in an asset, optionally linked to a taxon and region of interest.
- **Taxon:** A named biological concept from a source taxonomy or user namespace.
- **Suggestion:** An AI-produced candidate that has not been accepted as user metadata.
- **Embedding:** A model-specific numerical representation of an image or text.
- **Library:** A catalog database plus its associated storage and cache directories.
- **Plugin:** A versioned extension loaded through the documented plugin API.
- **Job:** Persistent background work with progress, cancellation, and recovery semantics.
- **Provider:** An AI execution backend such as CUDA, CPU, ONNX CUDA, or a future NPU backend.

## 10. Invariants

1. The UI thread performs no blocking disk, database, hash, metadata extraction, thumbnail generation, or AI inference work.
2. User-confirmed metadata always has precedence over AI suggestions.
3. Original files are never modified without a distinct, explicit future feature and corresponding design change.
4. SQLite is the authoritative metadata store.
5. Thumbnails, previews, extracted metadata caches, and vector indexes are rebuildable.
6. Every database schema change is performed by a numbered migration.
7. Application services depend on abstractions, not PySide6 widgets, SQLite calls, Torch objects, or plugin implementations.
8. Network activity is restricted to explicit update workflows.
9. Model-dependent data is always keyed by model identity and preprocessing identity.
10. A plugin may extend behavior but may not bypass transaction, job, permission, or provenance rules.

## 11. Quality gates before implementation

Documentation approval requires:

- consistent naming across all nine documents;
- no conflicting ownership of data or responsibilities;
- defined dependency direction;
- defined database authority and cache behavior;
- defined AI provenance and review behavior;
- defined plugin compatibility rules;
- defined configuration precedence and storage locations;
- a staged roadmap with completion criteria;
- coding rules that enforce the architecture.

## 12. Change control

After approval, architectural changes follow this order:

1. update the applicable design document;
2. record rationale, alternatives, and compatibility impact in its decision log;
3. obtain project approval when the change affects public APIs, persistence, plugin compatibility, offline guarantees, or scope;
4. implement and test the approved change.

Minor implementation details that do not alter documented contracts may be recorded in code-level documentation and tests.


## 13. Implementation status

Milestones 1–7 are implemented. The current repository version is 0.7.0. Taxonomy releases are installed from canonical, checksum-bound, Ed25519-signed offline packages. Package validation and hierarchy checks complete before one SQLite activation transaction. Stable taxon concept identifiers preserve observation references across source releases; observation revisions are append-only history. No architectural decision changed.

## Implementation status — Milestone 8

Milestone 8 is implemented in repository version 0.8.0. The implementation adds signed offline model packages, transactional model activation, provider-independent embedding contracts, optional Torch CPU/CUDA execution, versioned BioCLIP preprocessing, centralized GPU leases, adaptive CUDA out-of-memory retry, complete embedding provenance, exact cosine search, and atomic checksummed local vector-index generations. AI dependencies remain optional so ordinary catalog operation does not require Torch or a GPU.

## Implementation status — AI production runtime completion (0.8.1)

The Milestone 8 production runtime is complete at the repository-contract level. NatureAI Next now owns offline OpenCLIP/BioCLIP loading and tokenization, model residency and idle eviction, durable inference-run provenance, persistent embedding and vector-index jobs, checksum audits, atomic index activation, parity validation, corruption quarantine, and exact-search fallback. Optional AI dependencies remain isolated so catalog operation is unaffected when Torch, CUDA, OpenCLIP, or HNSWLib are unavailable.

## Implementation Status — Milestone 9
Milestone 9 AI Suggestions and Review core persistence and review workflow is implemented at repository-contract level in version 0.9.0. Suggestions are immutable provenance records; review decisions are append-only actions. Acceptance is always an explicit local-user command that creates a normal observation. Acceptance reversal is permitted only while that observation remains at the exact revision created by the review action. Prompt sets are versioned and checksummed, review paging is keyset-bounded, and near-duplicate grouping never deletes assets automatically.

## Implementation Status — Milestone 9 continuation (0.9.1)

Milestone 9 remains in progress. Repository version 0.9.1 adds a production prompt-set registry with semantic application compatibility checks and transactional activation; atomic multi-suggestion review transactions; append-only review audit and outbox events; explicit same-asset suggestion supersession; detailed review projections containing model, inference, prompt, geographic, score, and taxonomy provenance; occurrence-aware regional ranking; and text-semantic search orchestration through the existing validated vector-index fallback boundary. No architectural decision changed. Application services receive prompt loading, validation, checksum, and index-search behavior through injected ports/callables and do not import infrastructure adapters.

## Implementation status — repository version 0.9.2

Milestone 9 remains in progress. This increment adds migration 009, authoritative taxonomy text embeddings, deterministic invalidation, two-stage broad-group/taxonomy candidate generation, persistent near-duplicate review groups, singleton AI Review session state, a durable suggestion-generation job handler, and a PySide6 AI Review workspace that depends only on application and presentation services.

No architectural decision changed in this increment. SQLite remains authoritative, vector indexes remain rebuildable derivatives, AI output remains advisory, and all review decisions require explicit user commands.

## Implementation status — repository version 0.9.3

Milestone 9 remains in progress. This increment completes automatic extraction of scientific, vernacular, synonym, and broad-group labels from active taxonomy releases; bounded local text-embedding generation; atomic replacement through the authoritative taxonomy embedding store; and a cancellation-aware durable taxonomy text-embedding job. No architectural decision changed. Application orchestration depends on taxonomy label and embedding-store ports, while SQLite queries and AI provider execution remain adapters.


## Implementation status — repository version 0.9.4

Milestone 9 remains in progress. Taxonomy activation now has an application-level lifecycle hook that invalidates stale taxonomy text embeddings and submits deterministic, idempotent rebuild jobs for every active model variant and compatible active prompt set. Migration 010 records a deterministic generation identity and the active taxonomy release public IDs on each taxonomy text embedding. The coordinator remains provider-independent and depends only on application ports and the durable job command boundary. No architectural decision changed.


## Implementation status — Milestone 10 start (0.10.0)

The project owner approved the transition from Milestone 9 to Milestone 10. Any remaining Milestone 9 enhancements remain backlog items. The first Milestone 10 production increment implements metadata export through immutable plans, controlled read ports, read-only SQLite projections, deterministic JSON/CSV writers, atomic filesystem replacement, explicit collision handling, and provenance-complete results. Export execution performs no database writes and never modifies source originals or derivatives. No architectural decision changed.


## Implementation status — Milestone 10 continuation (0.10.1)

NatureAI Next now supports verified export of original files through a separate immutable plan and application service. The export catalog is read through a controlled read-only port; source files are streamed without modification, copied through a staging area, and verified against authoritative size and optional SHA-256 metadata before publication. Filename templates are token-allowlisted and normalized for Windows, collision behavior is explicit, and every completed export can include a deterministic checksummed manifest. Long-running original exports also have a versioned durable I/O job boundary. No architectural decision changed.

## Implementation status — repository version 0.10.2

Milestone 10 remains active. Original-file exports now support restart-safe execution through a persistent export-plan journal. The journal stores immutable plan content, deterministic output assignments, source checksums, per-item attempt and outcome state, and final manifest provenance. Completed outputs are checksum-validated before reuse; interrupted items return to pending; failed items are retried on the next explicit execution without recopying valid completed files. The existing direct read-only export API remains available for synchronous administrative use.


## Implementation status — repository version 0.10.3

Milestone 10 remains active. This increment adds a controlled derivative-export boundary with immutable plans, read-only catalog projections, EXIF-orientation-correct bounded JPEG/PNG rendering, optional standards-based XMP sidecars, deterministic naming and collision handling, checksummed package manifests, and an administrative CLI command. Derivative export does not mutate authoritative library state or source originals.

## Implementation status — Milestone 10 continuation (0.10.4)

The NatureAI Next v1.0 feature scope is frozen. `BACKLOG.md` is the sole repository location for ideas outside the approved architecture and roadmap; backlog entries cannot enter implementation without a future explicit scope decision.

This increment extends the existing persistent export journal to derivative exports. Immutable derivative item snapshots, deterministic image and XMP paths, attempts, output dimensions, sizes, and checksums now survive interruption. Completed image and XMP outputs are checksum-validated before reuse, interrupted items return to pending, and only failed or corrupt items are rerendered. Derivative rendering and hashing remain outside database transactions; short SQLite transactions own state transitions only. No architectural direction changed.

## Windows runtime hotfix — repository version 0.10.4.post2

The first production desktop feature is now connected to the existing import application service. The Qt shell exposes a File > Import folder action and an Imports workspace with managed, linked, and hybrid storage policies plus exact-duplicate handling. Planning, hashing, metadata extraction, managed copying, and catalog commits remain owned by `ImportService`; the Qt layer performs the operation on a worker thread and contains no direct SQLite or filesystem mutation logic. No architectural direction changed.


## Windows runtime hotfix — repository version 0.10.4.post3

Import planning isolates unsupported and corrupt source files per item. A ZIP archive, unreadable file, or undecodable image is persisted as a rejected import-plan item and reported in the final summary; it does not abort planning or execution for other files in the selected folder. Exact duplicate behavior remains unchanged.

## Implemented desktop catalog slice (0.10.4.post4)

The production desktop now exposes a read-only Library workspace backed by the catalog query port. It provides bounded keyset paging, asynchronous page and thumbnail loading, stable asset identity selection, imported asset counts, refresh after import, and a basic selected-asset preview and metadata projection. The Qt layer receives application services and thumbnail ports through the desktop composition root and does not query SQLite directly.

Import planning classifies recognized non-image containers such as ZIP and PDF files as `unsupported_format`; corrupt image payloads remain isolated as `image_decode_error`.

### Runtime correction 0.10.4.post5

The desktop catalog adapter must query only schema-defined derivative cache columns. Library browsing uses `derivative_cache_entries.relative_path`; schema/query parity is covered by an integration regression against a fully migrated library.

## Implemented desktop behavior update — 0.10.4.post6

The Library workspace owns both Qt threads and their worker objects until asynchronous work completes. Import completion requests a Library refresh and navigates to the Library workspace so results are immediately visible.

## Validated development baseline

Version `0.10.4.post6` is the authoritative Windows development baseline for subsequent work. It includes the installer, conservative uninstaller, cleanup utility, import workflow, and functional Library workspace validated on the target laptop. Later work must start from this release package or an explicitly superseding cumulative release.

## Implemented desktop behavior update — 0.11.0

The catalog derivative provider now owns persistent, deterministic thumbnail and preview caching inside each library's authoritative cache directories. Cache generation remains an infrastructure concern behind the existing thumbnail service boundary; Qt widgets receive bytes only and do not access the filesystem directly.

Thumbnail cache identity includes the canonical source path, source size, source modification timestamp, requested maximum dimension, output quality, and renderer identity. Source changes therefore invalidate cache identity without mutating or deleting source files. Cache entries are validated as bounded JPEG images before reuse and are rebuilt after corruption.

The Library workspace presents visible loading placeholders, visible failure state, and an explicit retry action. This behavior is part of the frozen v1.0 scope and does not add a new product feature.

## Implemented desktop behavior update — 0.11.1

The Windows installer now creates machine-local launchers and Windows shortcuts. Normal startup no longer requires a Conda command. The launcher resolves a validated last-used library from a versioned per-user launcher configuration; when none is valid, it uses the native Windows folder picker. Launcher configuration is stored outside all libraries and does not change the library schema. The installer may receive an explicit initialized library through `-DefaultLibrary`. The uninstaller removes launchers and shortcuts but preserves libraries and photographs by default.

## Implemented Windows product registration update — 0.11.2

NatureAI Next is registered per user under the standard Windows uninstall registry. The registration exposes the installed version, publisher, install location, display icon, repair command, and uninstall command to Windows Settings. Registration and repair do not require administrator rights and do not modify libraries or source photographs. Machine-local copies of repair and uninstall scripts are installed under `%LOCALAPPDATA%\NatureAI\NatureAI Next\Launchers`.

## Checked implementation status — 0.11.3

The Windows-validated desktop now includes a modeless, asynchronous full-image viewer. It reuses persistent preview derivatives, keeps decoding off the UI thread, supports bounded zoom and pan, and navigates the currently materialized Library ordering. No library schema or architectural boundary changed.


## Checked implementation status — 0.11.4

The Library inspector now edits human-confirmed catalog metadata through an application service and optimistic revision boundary. Title, caption, notes, rating, color label, pick state, and the complete user-tag set are committed atomically. The Qt layer owns only drafts and invokes the service on a worker thread; it does not access SQLite directly. Original photographs and embedded metadata remain immutable. BioCLIP and other AI results remain versioned suggestion evidence and cannot silently overwrite the human catalog fields. Existing libraries require no migration.

## Checked implementation status — 0.11.5

The Library workspace provides an offline quick-search boundary over filename/path, title, caption, user notes, and tags. Qt submits bounded asynchronous requests through `QuickSearchService`; the SQLite adapter owns FTS and filename matching and binds every user-derived value as a parameter. Clearing the field returns to standard catalog paging. Search results reuse the same thumbnail, selection, metadata, and Viewer workflows as normal Library rows. Human metadata and BioCLIP evidence remain separate.


## Checked implementation status — 0.11.6

The Library workspace now combines Quick Search with structured catalog filters for rating, color, pick state, capture date, dimensions, exact tags, and confirmed taxonomy names. The application layer converts filter values into the stable structured-query contract; SQLite owns parameterized compilation and bounded keyset paging. Taxonomy filters query confirmed observations and do not promote BioCLIP suggestions into human-confirmed metadata. Existing libraries require no migration.

## Checked implementation status — 0.11.7

Capture-date filtering uses a normalized `YYYY-MM-DD` calendar-date query. Authoritative UTC timestamps are converted to UTC calendar dates; EXIF local timestamps remain local calendar dates when no timezone is available. No timezone is invented.

## Release 0.12.0 desktop views

NatureAI Next supports persistent saved searches and manual collections as catalog-only organizational structures. Saved searches store the public versioned structured-query representation. Manual collections store references to assets and never copy or mutate original media. Both reopen through the same paged catalog projection used by the Library workspace.

### 0.12.1 accepted implementation scope
- Library locks persist owner PID, host, and creation time; only dead same-host owners are recovered automatically.
- Smart collections execute persisted structured queries dynamically.
- Collection metadata and membership management never modify original photographs.

### 0.12.7 accepted implementation scope
- Navigation and Inspector docks are recoverable from the View menu.
- Collections navigation routes to the live Library collection controls.
- Assigning selected photographs uses an explicit manual-collection chooser.


## Core pane docking policy (0.12.9)

Navigation and Inspector are deterministic core panes. Navigation is docked left and Inspector right. They may be hidden and restored through the View menu, but are not floatable top-level windows. Qt dock-state blobs are not persisted; window geometry, workspace, inspector visibility, sorting, and thumbnail size remain session settings.

## Desktop BioCLIP review integration (0.13.0)

The AI Review workspace is now composed into the production desktop against `SuggestionService` and `SqliteSuggestionStore`. It exposes immutable model-generated evidence through pending, deferred, accepted, rejected, and superseded queues. Accept creates or updates human-confirmed taxonomy through the existing audited review workflow; reject and defer change only AI review state. The workspace reports active local model and prompt-set identities, latest inference outcome, queue counts, confidence, provenance, execution provider, precision, and model variant. NatureAI Next does not download or invoke a cloud model. A library without an active local model or without generated suggestions remains fully usable and receives an explicit empty state.


### Accepted AI generation boundary

Local BioCLIP suggestion generation is always user initiated, offline, auditable, and selection scoped. It requires installed and activated local model, prompt, and taxonomy embedding resources. Suggestions are evidence only and never overwrite human metadata.

## Local AI resource installation

The desktop shall provide a user-controlled offline resource manager for signed model packages, validated prompt manifests, signed taxonomy packages, and taxonomy text embedding preparation. Resource installation must never trigger an implicit download or cloud request. The library writer lock must be released from the Qt shutdown signal and remain safe under repeated close calls.

## Local AI resource supply chain

AI resources must be explicitly acquired, packaged, signed, verified, and installed locally. NatureAI Next does not silently download or trust model weights, prompt sets, or taxonomy data. The supported resource-packaging interface is `natureai-next-resources`; its package formats are the only formats accepted by the local AI resource manager.

## 0.13.5 resource workspace and command discovery

The Windows installer manages the active NatureAI environment and Scripts directories in the current-user PATH. Local AI resource workspaces are generated with absolute paths by `natureai-next-resources workspace-init`, preventing current-directory-dependent package builds.

## 0.13.6 guided BioCLIP resource setup

The desktop provides a guided, explicit-consent workflow that can acquire or import the official BioCLIP checkpoint, create local trust material, build and activate signed model resources, convert a user-supplied taxonomy CSV into a signed taxonomy resource, create a compatible prompt set, and build taxonomy embeddings. Generated files use absolute workspace paths and remain locally auditable. No photographs are uploaded and no cloud inference is used.

## Regional knowledge acquisition
Version 0.14.1 adds user-initiated acquisition of regional occurrence evidence and taxonomy. The resulting resources are signed and installed locally. The application must not require manual manifest editing or resource file browsing in the normal workflow.

## Observation Intelligence

Confirmed taxonomy creates stable observations. Photographs are immutable evidence and multiple assets may link to one observation. Personal history is displayed separately from AI and regional evidence.


## Observation workspace invariant
Observation History is based on confirmed observations rather than individual AI suggestions. Multiple photographs may support one stable observation identity, and original photographs remain immutable.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.

## R3 map and export integration

Aperture shall present eligible adjacent raster map packages on a continuous geographic canvas without removing existing map controls or vector-map support. Aperture shall also support atomic portable export packages containing generated report/data artifacts and optional selected originals for all built-in media types, with explicit missing-original policy and a checksummed manifest.

### Composite offline map requirement

All-mode rendering must select packages by geographic footprint and zoom role, not by tile existence. Regional packages must not contribute buffered low-zoom tiles to country views. Country/global overview packages provide low-zoom coverage; regional detail begins at zoom 9 unless future package metadata declares a stronger role explicitly.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.

## UI layout preservation requirement — collapsible lower panel

The Photos workspace, and each comparable subject workspace using the shared canonical-enrichment/review panel, shall allow the lower panel to collapse to approximately one compact line and expand back to its full current content. This shall be a presentation-only change. Existing import, enrichment, model, review, viewer, refresh, selection, provenance, data-retention, and removal behaviour shall remain operational and unchanged. Collapsing shall not destroy or recreate active state. See `UI_COLLAPSIBLE_LOWER_PANEL_REQUIREMENT.md`.
A Fieldora whiteboard is an offline Excalidraw-compatible document stored under
the library's Documents area. Whiteboard revisions and snapshots are owned by
Documents, not by the Science database. The former Science whiteboard tables
remain untouched for compatibility; Fieldora does not migrate, convert, or
delete existing custom whiteboards.
