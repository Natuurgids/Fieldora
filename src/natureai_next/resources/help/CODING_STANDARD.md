# NatureAI Next — Coding Standard

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. Scope

This standard applies to all production Python, tests, build scripts, database migrations, plugin API code, and PySide6 UI code in NatureAI Next.

The goals are correctness, stable architecture, maintainability, predictable performance, and safe offline behavior.

## 2. Language and tooling baseline

- Python 3.11 only until the project formally changes the baseline.
- Source layout under `src/`.
- `pyproject.toml` is the primary project configuration.
- Code formatting and linting use a single automated toolchain selected during Milestone 1.
- Static typing is mandatory for production code.
- Type checking runs in strict mode for core domain, application, ports, and plugin API packages; infrastructure exceptions require documented justification.
- Tests use pytest or the approved equivalent.
- Qt-specific tests use a maintained PySide6-compatible test adapter.

Exact tool versions are pinned in environment/lock files and updated deliberately.

## 3. Architecture enforcement

Allowed dependency direction:

```text
shared <- domain <- ports/application <- infrastructure/ui/plugins/bootstrap
```

More precisely:

- `domain` may depend only on standard library and approved dependency-free `shared` modules.
- `ports` may depend on domain and shared types.
- `application` may depend on domain, ports, and shared.
- `infrastructure` implements ports and may use external libraries.
- `ui` depends on application-facing services and presentation models, not infrastructure implementations.
- `bootstrap` may depend on all modules solely to compose them.
- plugin implementations depend only on the public plugin API and their own dependencies.

Import cycles are prohibited. Import-lint rules are part of CI.

## 4. Code organization

- One module has one coherent responsibility.
- Avoid files above approximately 500 logical lines; larger files require a cohesion review, not mechanical splitting.
- Public interfaces are placed near their domain and re-exported intentionally.
- No wildcard imports.
- No runtime path manipulation.
- No side-effectful work at module import time beyond constants and lightweight registration declarations.
- Global mutable singletons are prohibited except immutable registries created in the composition root.

## 5. Naming

- Packages/modules/functions/variables: `snake_case`.
- Classes/protocols/exceptions: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Private implementation names begin with `_`.
- Stable command, event, error, and plugin IDs use lowercase dotted namespaces.
- Database names use lowercase `snake_case`.
- Boolean names read as predicates: `is_available`, `has_embedding`, `should_retry`.
- Avoid unexplained abbreviations.

## 6. Types and data models

- Every public function and method has complete parameter and return annotations.
- Prefer immutable dataclasses for commands, events, value objects, and results.
- Use enums for closed domain states; serialized enums must handle unknown future values at compatibility boundaries.
- Use `Protocol` for structural ports where appropriate.
- Avoid `Any`; isolate unavoidable dynamic library boundaries and validate immediately.
- Do not pass unstructured dictionaries across stable boundaries when a typed model is appropriate.
- Use `pathlib.Path` internally for filesystem paths, converted at serialization boundaries.
- Use timezone-aware UTC instants and explicit local-time value objects.

## 7. Functions and control flow

- Functions should express one level of abstraction.
- Prefer early validation and clear guard clauses.
- Avoid boolean-flag functions that perform unrelated modes; use distinct commands or strategy objects.
- Avoid hidden I/O in properties.
- Iteration over potentially large data sets must be streamed or paged.
- Never use an unbounded list where the data size may scale with the library.
- Public methods document transactional, threading, and I/O behavior when non-obvious.

## 8. Error handling

- Do not catch `Exception` unless at a process, job, plugin, or UI boundary where it is logged and converted.
- Never use bare `except`.
- Expected failures use typed exceptions or result objects with stable error codes.
- Preserve exception chaining with `raise ... from ...`.
- Do not expose raw tracebacks to ordinary users.
- Cancellation is distinct from failure.
- Retry only failures classified as transient and only with bounded policy.
- Logging an exception does not by itself constitute handling it.

## 9. Logging

Structured logs include:

- timestamp;
- severity;
- subsystem;
- correlation ID;
- job ID where applicable;
- plugin ID/version where applicable;
- stable error code;
- sanitized context.

Rules:

- no image content or embedding vectors in logs;
- no secrets;
- avoid full user paths at normal levels where a path token or filename is enough;
- no duplicate logging at every layer;
- performance-sensitive loops use aggregated metrics, not per-item info logs.

## 10. Database coding rules

- SQL exists only in database infrastructure and migration modules.
- Use parameterized SQL exclusively.
- Application services own transaction boundaries through unit of work.
- Repositories do not call commit independently.
- No transaction remains open during filesystem copying, hashing, decoding, or inference.
- Every foreign key has an explicit delete policy.
- Every schema change has a migration and migration test.
- Large queries use keyset pagination.
- Performance-sensitive queries require query-plan tests or benchmark evidence.
- Database row models are not domain entities unless explicitly mapped.

### 10.1 Subsystem database build rules

Before adding persistent data, every feature design must answer:

1. Who owns the data: the core library or an optional subsystem?
2. Is the data required to preserve the meaning of the library when the feature is unavailable?
3. Can the data be rebuilt from authoritative core records or external packages?
4. Does the feature require an independent migration, integrity, backup, or retention policy?

The following rules are mandatory:

- Do not add optional or feature-specific tables to the core library by default.
- Create or open an optional subsystem database only when its feature is activated or an existing workspace references it.
- Each subsystem has a stable dotted identifier, its own schema-version history, migrations, connection factory, repositories, integrity check, and health state.
- Core and subsystem migrations are independent. A migration number is meaningful only within its owning database.
- Cross-database references use stable public IDs. Never persist another database's internal integer primary key as a durable external reference.
- Do not depend on cross-database foreign-key enforcement. Validate references at application boundaries and tolerate temporarily unavailable targets.
- A subsystem repository may not issue SQL against another subsystem's tables. Cross-subsystem workflows are coordinated by application services through typed ports.
- Optional subsystem activation must be idempotent, concurrency-safe, and recoverable after interruption.
- A failed optional subsystem must not prevent the core library from opening. Disable or degrade only the affected capability and expose repair or reactivation actions.
- Derived caches, thumbnails, map tiles, vector indexes, embeddings, and search indexes are not authoritative core data and must be rebuildable or replaceable.
- Essential user knowledge must not exist only in a disposable cache. Accepted conclusions and durable links are written to their authoritative owner.
- Database file locations, ownership, retention, portability, backup, and deletion behavior must be documented before implementation.
- Tests must cover first activation, repeated activation, migration, missing database, corrupt database, incompatible schema, read-only storage, and feature-disabled startup.
- The composition root owns subsystem registration and activation. Feature modules must not create database files ad hoc.

Default placement guidance:

- **Core library:** assets, file instances, import provenance, observations, explicit observation time/location, evidence links, durable monitoring-site identity, and stable external references.
- **Taxonomy subsystem:** shared authoritative taxonomy releases, synonyms, source datasets, distribution reference data, and update metadata.
- **Map subsystem:** offline package catalog, tile/vector coverage, reverse-geocoding indexes, cache manifests, map-provider settings, and UI-only map bookmarks.
- **Project subsystem:** project registration, participants, assignments, schedules, protocols, workflow state, and project reports.
- **AI subsystem:** embeddings, similarity indexes, model-specific features, inference caches, and locally learned retrieval structures.
- **Audit subsystem:** high-volume activity, diagnostics, performance history, and rotatable operational records.

A feature may deviate from this guidance only through an accepted architecture decision that explains why the data is intrinsic to the core library.

## 11. Filesystem rules

- Original files are opened read-only.
- Writes use temporary files in the destination filesystem, flush, optional fsync according to durability class, then atomic replace where supported.
- Path comparisons use normalized Windows-aware keys while preserving display form.
- Never assume case sensitivity.
- Handle long paths through supported Windows APIs and packaging settings.
- Validate user-controlled export templates and paths.
- File deletion follows recorded intent and recovery rules.

## 12. Concurrency and threading

- Qt widgets and GUI objects are UI-thread only.
- Database connections are thread-confined.
- Torch model instances are owned by the AI worker/provider coordinator unless documented safe otherwise.
- Shared mutable state requires an explicit owner and synchronization strategy.
- Prefer message passing and immutable values.
- Every long-running operation supports progress and cancellation where meaningful.
- Do not block the UI thread with `sleep`, file I/O, database calls, futures waiting, or inference.
- Async, thread, and process boundaries must be visible in function or class documentation.

## 13. PySide6 rules

- Use Qt model/view for large collections.
- Do not create one widget per thumbnail.
- Signals carry stable IDs or immutable data, not repositories or database rows tied to a connection.
- Disconnect or lifetime-guard long-lived signal connections.
- Use parent ownership consistently for QObjects.
- Business logic belongs in application services or view models, not widget event handlers.
- UI text is translatable.
- Colors and spacing come from the design system or palette, not feature-local literals.

## 14. AI coding rules

- Model-specific code remains in provider adapters.
- Preprocessing is versioned and tested.
- Application boundaries do not expose Torch tensors.
- Inference runs record model, preprocessing, provider, precision, and parameters.
- Batch size is bounded and adaptive only through documented policy.
- CUDA out-of-memory errors trigger controlled cleanup and bounded retry.
- Raw model scores are not labeled probabilities without calibration.
- AI results never directly mutate confirmed metadata.

## 15. Plugin coding rules

Core code exposed to plugins must be in the public plugin API package. Internal symbols are not compatibility promises.

Plugin handlers:

- are idempotent for event delivery;
- use namespaced IDs;
- use approved storage services;
- do not modify originals;
- do not access core tables directly;
- submit long work through jobs;
- declare capabilities accurately.

## 16. Security and offline rules

- No general network library use outside update infrastructure and approved restricted update adapters.
- A CI/static check scans for unauthorized network imports in production packages.
- Downloaded packages require checksum verification and appropriate signature verification.
- External processes use argument arrays, never shell-concatenated user input.
- Deserialize only validated formats; arbitrary pickle loading is prohibited for untrusted artifacts.
- Model loading policy must account for unsafe serialization formats and trusted package sources.

## 17. Documentation

- Public APIs have docstrings describing purpose, parameters, return value, errors, thread behavior, and transactional behavior where relevant.
- Comments explain why, not restate what.
- Architectural decisions belong in the source-of-truth documents before code.
- User-visible behavior changes update documentation in the same change.
- No stale TODO markers in production code. Deferred work belongs in tracked planning with no incomplete code path.

## 18. Testing standard

Every module must compile. Tests are proportional to risk.

Required categories:

- domain and application unit tests;
- port/adapter contract tests;
- database migration tests;
- filesystem failure tests;
- job cancellation/recovery tests;
- plugin compatibility tests;
- AI regression and tolerance tests;
- GUI view-model tests;
- performance tests for hot paths.

Tests must be deterministic. Time, UUIDs, filesystem, and provider selection are injected where determinism matters.

Do not use real network access in tests except isolated update-transport tests against a local controlled server.

## 19. Performance standard

- Measure before optimizing, but design hot paths for scale from the beginning.
- Avoid N+1 database queries.
- Avoid repeated image decode and model preprocessing.
- Use bounded caches with metrics.
- Batch database and inference work.
- Use memory-mapped or streaming techniques only behind clear adapters and benchmarks.
- Performance regressions beyond agreed thresholds fail the relevant benchmark gate.

## 20. Dependencies

A new dependency requires review of:

- license;
- maintenance health;
- Windows and Python 3.11 support;
- offline packaging;
- binary size;
- startup impact;
- security history;
- API stability;
- replacement cost.

Prefer well-maintained focused dependencies. Do not reimplement complex standard functionality merely to avoid a justified dependency.

## 21. Git and change quality

- Changes are cohesive and reviewable.
- Commit messages describe intent.
- Generated files are clearly identified.
- Database migrations are never rewritten after release.
- Public API changes include compatibility notes.
- Refactoring is separated from behavior changes where practical.
- No drive-by architectural refactors without an approved design update.

## 22. Definition of acceptable production code

Production code is acceptable only when it:

- implements the complete approved behavior;
- has no placeholder or silent fallback that hides missing functionality;
- preserves documented invariants;
- is typed and test-covered according to risk;
- handles expected failure modes;
- is observable and cancellable where applicable;
- does not introduce unauthorized network access;
- performs acceptably at intended scale;
- keeps stable APIs coherent.

### Offline map source rules

- Never implement bulk or background downloads from OpenStreetMap's public tile
  service for offline use.
- Offline packages must be local, explicitly registered, verified, and enabled.
- Provider-specific licences and visible attribution are mandatory package data.
- Tile readers must be read-only and must not mutate third-party packages.
- Map-package failure must remain isolated from the core library.
- The application-facing map API uses XYZ coordinates; providers are responsible
  for translating to package-native schemes such as MBTiles TMS rows.

## Temporal-map rules

- Never connect independent observations into an animal route by default.
- Label temporal output as observed locations, inferred distribution, or confirmed movement.
- Confirmed movement requires an explicit series and identity/tracking evidence.
- Preserve observation timestamps and coordinates as authoritative core-library data.
- Store playback caches and UI preferences only in optional map storage.
- Temporal queries must support bounded snapshot and cumulative modes; trail mode must require a series identifier.

### Taxonomy reference subsystem rules

- Rich, redistributable taxonomy datasets belong to `taxonomy.reference`, not to every library.
- Core observations reference taxa by stable public identifier; cross-database integer keys are forbidden.
- A library must open and observations must remain readable when `taxonomy.reference` is inactive or unavailable.
- Dataset activation is versioned and atomic: installing a newer version may deactivate an older version from the same source but must not rewrite historical observation evidence.
- Taxon facts, names, distributions, and links must retain source attribution.
- Knowledge Center reference pages are projections over the taxonomy subsystem plus core observations; they do not own authoritative records.

### Knowledge Center build rules

- Knowledge Center views are application projections, not persistence owners.
- Combine subsystem and core-library data through ports and stable public IDs; never attach databases for cross-file SQL joins.
- Reference facts retain their source and attribution. Local observations retain their evidence and confirmation state.
- A taxon that has no local observations must still be browsable; a local observation with unavailable reference data must remain usable.
- Derived counts and date ranges are calculated from authoritative observations and are not copied into `taxonomy.reference`.

## Authoritative taxonomy package rules

- Never treat an AI model label list as the authoritative taxonomy.
- Install reference taxonomy only after package signature, checksum, schema, application-version, and licence validation.
- Reject distributable Aperture packages whose data licence does not allow redistribution.
- Preserve source name, source version, source URL, licence URL, attribution, checksum, and package schema version.
- Store accepted Latin names independently from common names.
- Every common name must retain language, optional region, source, preference, and verification state.
- BioCLIP and future model labels must map through `ai_taxon_label_mappings`; do not overwrite the original model label or model version.
- Do not invent or machine-translate a missing common name as though it were authoritative.

### Taxonomy naming rules

- Use the reference taxon public ID and accepted scientific name as identity.
- Treat common names as language- and region-scoped display metadata.
- Never invent or silently translate a missing common name.
- Dataset disablement must be reversible and must not delete package provenance.
- UI preferences must not rewrite authoritative taxonomy or observation records.

## Asset analysis and enrichment rules

1. Every analysis execution must target one stable asset public ID and create a new `asset_analyses` record.
2. Do not add model-specific output columns to `assets`.
3. Record engine ID, engine family, model name/version, configuration JSON and hash, source SHA-256 when known, application version, and execution timestamps.
4. Completed analyses are historical records. A rerun or changed model creates another analysis.
5. Lightweight results needed to understand the photo offline belong in normalized core-library tables.
6. Large or rebuildable artifacts belong in optional analysis databases or managed files and must be linked by stable identifiers.
7. A candidate becomes authoritative knowledge only through an explicit promotion workflow linked to an observation.
8. Analysis records from different engines or versions may coexist and must not silently supersede each other.
9. Cross-database references use public IDs; optional AI data must never be required to open the core library.
10. Tests must cover multiple analyses per asset, provenance retention, and traceable promotion.

## Asset-removal rules

- Trash and permanent deletion are separate operations.
- Permanent deletion requires the asset to be in Trash.
- Always generate a dependency preview before presenting permanent deletion.
- Never silently remove evidence from an authoritative observation.
- Use database cascades for asset-owned records; do not hand-maintain incomplete deletion lists.
- Cancel queued or running asset-specific jobs before deleting the asset.
- Remove managed originals and registered thumbnail/preview files, and retain a purge audit outcome.
- Optional subsystem cleanup must use stable public IDs and must not prevent core cleanup from being reported accurately.

### Knowledge Engine and capability rules

- UI workspaces consume application projections, not repositories from multiple domains.
- Cross-domain synthesis belongs in `KnowledgeEngine` services and must not own authoritative data.
- Optional capabilities register descriptors and activators without performing startup I/O.
- Capability dependencies are explicit and activated lazily.
- Evidence projections must explain the principal records supporting a result.

## Knowledge Engine workspace rule

Desktop workspaces that need information from more than one domain must request a Knowledge Engine projection. Observation History must not coordinate observation, taxonomy, analysis, or map repositories itself. AI Review may use its suggestion decision service directly, but local observation context and photo-wide enrichment history must come from the Knowledge Engine. New workspace code must not introduce direct cross-domain repository composition.

## Workflow, event, and retention rules

- Long-running multi-step operations must be registered as versioned workflow definitions over durable jobs.
- Every workflow step must have a stable step ID and idempotency key.
- Dependencies must point to earlier steps; circular or implicit dependencies are prohibited.
- Optional steps must be declared explicitly and may not silently change authoritative results.
- Cross-capability state changes must use typed domain events rather than direct repository calls.
- Event handlers must be independently failure-isolated and idempotent where durable redelivery is possible.
- Every workflow or capability that creates temporary or rebuildable data must declare ownership, storage location, retention period, and cleanup behavior.
- Cleanup must never remove queued, running, paused, or interrupted work.
- Cleanup services must support a dry-run summary and report reclaimed storage.
- Authoritative library data is outside generic workflow cleanup; it can be removed only through its domain-specific deletion workflow.

## Lean offline runtime rules

- Aperture workflow execution is embedded in the desktop process and uses the existing SQLite durable-job store.
- Workflow steps may declare only `io`, `cpu`, or `gpu` resource classes.
- External brokers, schedulers, cache servers, database servers, workflow servers, and always-running daemons are prohibited for Version 2 core functionality.
- In-process typed events are preferred for same-process integration; the SQLite outbox is used only when restart-safe delivery is required.
- New dependencies must be justified by a direct user benefit and must not duplicate Python, Qt, SQLite, or filesystem capabilities already present.
- Optional capability failure must not prevent the core Aperture Library from opening.
- Rebuildable caches, indexes, and temporary artifacts must declare bounded cleanup and may never become the sole copy of authoritative data.

## Cleanup implementation rules

- Every destructive cleanup operation must have a dry-run or preview equivalent.
- Cleanup scanners may traverse only explicit Aperture-owned roots supplied by composition.
- Symbolic links and unknown external paths must not be followed or deleted.
- Authoritative domain records and installed reference packages are never routine-retention targets.
- Cleanup reports must include item counts and reclaimed bytes; failures must not be reported as reclaimed storage.

## Maintenance and work-control rules

- Add Version 2 health checks to `LibraryHealthService` or another established Maintenance Center service; do not create a parallel health subsystem.
- Pause, continue, stop, retry, and interrupted-work recovery must use the existing durable job state machine.
- A health inspection must not create or activate an unused optional subsystem database.
- Maintenance inspection is read-only by default. Repairs and cleanup require an explicit command and must preserve authoritative data.
- UI surfaces may present job state and invoke application commands, but must not update job rows directly.

### Maintenance inventory rules
- Storage inventory may scan only Aperture-owned paths and must not follow symbolic links.
- Optional subsystem catalogs must be inspected read-only and must not be activated merely for display.
- Authoritative and rebuildable storage must be identified separately.
- Inventory actions are informational; destructive or mutating actions require an explicit feature-specific workflow.
