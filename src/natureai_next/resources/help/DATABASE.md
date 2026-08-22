## Science database

`science.sqlite3` is an authoritative, optional subsystem database. It owns projects,
dossiers, dossier-media references, scientific artifacts and measurements, calendar
activities, and whiteboard notes. It uses WAL mode, foreign keys, bounded busy waiting,
and transactions confined to Science.

Media references contain stable asset public IDs. Science does not attach, join, or
write `library.sqlite3`, and no foreign key crosses the database boundary. Backup,
restore, health, and migration registration are required before Science is considered
production-safe; this gap is tracked in `docs/AUDIT_0.03.md`.

## Release 3 backup inventory requirement

Backup and restore cover the complete selected set of Aperture-owned databases, including core, media, enrichment, reporting, taxonomy, maps, and other active subsystem databases. Complete-library backup is the default. Active-library-type and custom backups are explicit scoped archives with dependency closure for shared observations, notes, collections, and relationships. Integration/model databases and caches are excluded; accepted normalized enrichment is included. Snapshots use coordinated writer quiescence and SQLite online backup.

# NatureAI Next — Database Design

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. Database role

SQLite is used through an authoritative core library database plus lazily activated subsystem databases. The core library is authoritative for assets, file instances, imports, observations, essential observation context, and durable references. Optional capabilities own separate databases for data such as shared taxonomy releases, offline-map indexes, project administration, AI indexes, and high-volume audit history. Original photographs, large derivatives, map packages, and rebuildable caches remain on the filesystem.

The schema is designed for at least 100,000 assets and should remain viable at 1,000,000 assets on the reference workstation without a fundamental redesign.

## 2. SQLite configuration

Each library always uses one core `library.sqlite3` database. Optional subsystem databases are created or opened only when their capability is activated or an existing workspace requires them. Subsystems have independent migration histories and must not be required for ordinary core-library startup.

Required connection configuration:

- WAL journal mode;
- foreign keys enabled;
- busy timeout configured;
- synchronous mode `NORMAL` by default, configurable to `FULL` for maximum durability;
- temp storage in memory when safe;
- application-controlled page cache;
- explicit transactions;
- periodic passive checkpoints and controlled truncate checkpoints during maintenance.

Connections are thread-confined. A connection factory creates read-only or read-write connections according to use case.


### 2.1 Database ownership and activation

Database ownership is determined before schema design:

- core records are necessary to preserve and interpret the library without optional capabilities;
- subsystem records support an optional capability, can be independently migrated, or are rebuildable from authoritative data;
- cross-database links use public UUIDs rather than internal integer keys;
- the application layer coordinates cross-database consistency;
- optional subsystem errors degrade only the owning feature;
- the composition root activates subsystem databases through a registry rather than feature-local file creation.

Representative subsystem identifiers are `taxonomy.reference`, `maps.offline`, `projects.workspace`, `ai.knowledge`, and `audit.activity`. Their physical filenames and locations are configuration and deployment details, not domain contracts.

## 3. Identity strategy

Most persisted entities use:

- `id INTEGER PRIMARY KEY` as an efficient internal key;
- `public_id TEXT NOT NULL UNIQUE` containing a locally generated UUID for stable external references.

Internal foreign keys use integer IDs. Public APIs, plugin events, exports, and logs use public IDs unless a contract explicitly states otherwise.

Content hashes use lowercase hexadecimal SHA-256. Fast preliminary fingerprints may assist import planning but never replace the canonical hash for duplicate identity.

## 4. Time representation

- Absolute timestamps are stored as integer microseconds since Unix epoch UTC.
- Capture time includes source timezone information and certainty fields.
- User-entered local times without a known timezone preserve the local wall time separately.
- Dates with incomplete precision are represented by explicit precision, not guessed values.

## 5. Schema migration

- Migrations are numbered, immutable, and applied in order.
- Each migration runs inside a transaction when SQLite permits.
- Destructive or long-running migrations create a verified pre-migration backup.
- The database records schema version, application version, start/end time, and migration checksum.
- Production downgrade migrations are not supported. Recovery uses a backup and compatible application version.
- Plugin schema changes use plugin-owned namespaced migrations and may not alter core tables.

## 6. Core schema groups

The following table definitions are logical contracts. Exact DDL may add indexes, checks, generated columns, and SQLite compatibility details without changing semantics.

### 6.1 Library and schema metadata

#### `library_info`

Single-row logical record:

- library public UUID;
- creation timestamp;
- current schema version;
- minimum compatible application version;
- display name;
- default locale;
- active taxonomy release IDs;
- integrity state.

#### `schema_migrations`

- migration number;
- name;
- checksum;
- applied timestamp;
- application version;
- execution duration.

### 6.2 Assets and files

#### `assets`

- internal and public identity;
- media type;
- lifecycle state (`active`, `trashed`, `purged`);
- primary file instance ID;
- capture time normalized fields;
- rating;
- color label;
- pick state;
- title;
- caption;
- user notes;
- created and modified timestamps;
- optimistic revision number.

#### `file_instances`

- asset ID;
- storage mode (`managed`, `linked`, `derivative`);
- role (`original`, `alternate`, `sidecar`, `preview`, `thumbnail`, `export`);
- normalized path and case-folded path key;
- file size;
- modified time observed;
- canonical SHA-256;
- optional fast fingerprint;
- availability state;
- MIME type and format;
- import source path;
- verification timestamp;
- created and modified timestamps.

A unique constraint prevents duplicate active path keys. Hash indexes support duplicate lookup.

#### `image_properties`

One-to-one with an asset or file instance as defined by importer policy:

- pixel width and height;
- orientation;
- bit depth;
- color space;
- alpha presence;
- camera make and model;
- lens;
- exposure fields;
- original metadata snapshot reference.

#### `metadata_snapshots`

Stores compressed, size-bounded original metadata payloads or normalized key/value representations. Binary payload size limits prevent database abuse.

### 6.3 Tags and collections

#### `tags`

- public identity;
- canonical normalized name;
- display name;
- optional parent tag;
- optional color;
- created timestamp.

Tag name uniqueness is case-insensitive within a parent.

#### `asset_tags`

Many-to-many relation with source (`user`, `import`, `plugin`) and created timestamp.

#### `collections`

- identity;
- type (`manual`, `smart`);
- name and description;
- smart-query JSON and query schema version;
- sort mode;
- timestamps.

#### `collection_assets`

Manual membership with stable position key and added timestamp.

### 6.4 Geography

#### `locations`

Reusable place records:

- point latitude/longitude;
- optional altitude and accuracy;
- country code;
- administrative areas;
- locality;
- place name;
- source and confidence;
- optional geometry reference for future polygon support.

Coordinates are validated by checks. Geographic search uses an SQLite RTree virtual table keyed to location IDs for bounding-box queries.

#### `asset_locations`

Links an asset to a location with role (`capture`, `subject`, `user_defined`) and precedence.

### 6.5 Taxonomy

#### `taxonomy_sources`

- source identity and name;
- source version;
- package checksum;
- license metadata;
- installation and activation timestamps;
- active flag.

#### `taxa`

- source ID;
- source taxon identifier;
- stable concept public ID;
- scientific name;
- authorship;
- rank;
- parent taxon ID;
- accepted taxon ID for synonyms;
- status;
- kingdom and major group denormalizations for filtering;
- extinction flag where supplied.

The source identifier is unique within a taxonomy source. Hierarchy traversal uses parent indexes and a closure table.

#### `taxon_closure`

- ancestor taxon ID;
- descendant taxon ID;
- depth.

Rebuilt transactionally when a taxonomy package is activated.

#### `taxon_names`

- taxon ID;
- language tag;
- region code;
- name;
- name type;
- preferred flag;
- source.

#### `taxon_regions`

- taxon ID;
- region code or geographic unit;
- occurrence status;
- source.

#### `user_taxa`

Separate namespace for provisional or custom concepts. User taxa can later be mapped to an imported taxon without rewriting observation history.

### 6.6 Observations and annotations

#### `observations`

- identity;
- asset ID;
- confirmed taxon ID or user taxon ID, mutually constrained;
- observation type (`organism`, `habitat`, `landscape`, `unknown`);
- life stage, sex, count, behavior, and notes where applicable;
- confirmation state;
- source (`user`, `import`, `plugin`);
- region-of-interest ID;
- timestamps;
- revision.

An asset may contain multiple observations.

#### `regions_of_interest`

- asset ID;
- shape type;
- normalized coordinates encoded as validated JSON or dedicated columns;
- label;
- created source;
- timestamps.

Coordinates are normalized to the orientation-corrected image coordinate system.

### 6.7 AI models and inference

#### `model_packages`

- model identity and semantic version;
- model family;
- artifact checksum;
- manifest JSON;
- license metadata;
- install path token;
- installation state;
- installed timestamp.

#### `model_variants`

- package ID;
- variant identity;
- runtime (`torch`, `onnx`);
- precision;
- device requirements;
- preprocessing identity;
- embedding dimension;
- active flag.

#### `inference_runs`

- job ID;
- model variant ID;
- execution provider;
- parameter JSON;
- application version;
- started/completed timestamps;
- outcome and error code.

#### `embeddings`

- asset ID;
- model variant ID;
- preprocessing identity;
- crop/region ID if applicable;
- vector dimension;
- scalar type;
- normalized flag;
- compressed vector blob;
- vector checksum;
- created timestamp.

A unique constraint prevents duplicate current embeddings for the same asset/region/model/preprocessing combination.

#### `ai_suggestions`

- asset or observation target;
- inference run ID;
- suggestion type;
- candidate taxon or label;
- raw score;
- rank;
- optional calibrated score and calibration identity;
- explanation/provenance JSON;
- review state (`pending`, `accepted`, `rejected`, `superseded`);
- reviewed timestamp and user action reference.

Accepted suggestions create or update user-owned domain records through application services; the suggestion row remains as provenance.

### 6.8 Search

#### `asset_search_fts`

FTS5 virtual table containing normalized searchable text derived from:

- title, caption, and notes;
- tags;
- scientific and common names;
- place names;
- selected imported metadata.

Updates occur through outbox handlers, not ad hoc widget logic. A rebuild command verifies parity.

#### Saved query representation

Smart collection and saved-search queries are JSON abstract syntax trees with an explicit schema version. The query compiler permits only documented fields and operators.

### 6.9 Jobs and events

#### `jobs`

- public identity;
- type and payload version;
- payload JSON;
- state;
- priority;
- resource class;
- idempotency key;
- parent/dependency fields;
- progress current/total/unit/message;
- attempt count and retry time;
- timestamps;
- error code and diagnostic reference;
- result JSON.

#### `job_items`

Optional per-item state for large batch jobs, allowing isolated retries without enormous job payloads.

#### `event_outbox`

- event public ID;
- event type and schema version;
- aggregate public ID;
- payload JSON;
- created timestamp;
- dispatch state and attempt count.

#### `audit_log`

Records material user-visible changes:

- action identity;
- actor (`user`, `system`, plugin ID);
- action type;
- target identity;
- before/after summary or patch;
- timestamp;
- correlation ID.

Sensitive raw file metadata is not duplicated unnecessarily.

### 6.10 Plugins

#### `installed_plugins`

- plugin ID and version;
- manifest checksum;
- enabled state;
- compatibility status;
- granted capabilities;
- install timestamp;
- last load result.

#### Plugin-owned tables

Plugin tables must begin with `plugin_<normalized_plugin_id>__`. Plugins use core-provided migration services and cannot alter core tables or triggers.

## 7. Index strategy

Required relational indexes include:

- asset lifecycle, capture time, rating, and modified time;
- file path key, hash, and availability;
- observation asset and taxon;
- taxonomy parent, accepted-name, rank, and source identifier;
- tag normalized name;
- job state/priority/retry time;
- outbox dispatch state;
- embedding model and asset uniqueness.

Composite index order is determined from measured query plans. Every non-trivial query added to a performance-sensitive path must include an `EXPLAIN QUERY PLAN` test or benchmark evidence.

## 8. Vector index

Embedding blobs in SQLite are authoritative. Approximate nearest-neighbor indexes are stored under `indexes/vectors/` and are rebuildable.

Initial index adapter:

- HNSW-based local index where packaging is stable;
- one index per model variant and preprocessing identity;
- mapping between HNSW labels and asset/region IDs persisted in SQLite;
- atomic index generation followed by manifest swap;
- checksum and row-count validation at open;
- exact chunked NumPy fallback when the index is missing or invalid.

The fallback guarantees correctness, although it may be slower.

## 9. Concurrency and transactions

- UI reads use short-lived snapshots.
- Application commands use explicit unit-of-work transactions.
- Long filesystem or AI operations never hold a database transaction open.
- Jobs use prepare/execute/commit phases: reserve work, perform external work, then commit results.
- Optimistic revisions detect conflicting metadata edits.
- Bulk writes use bounded batches, normally 100–1,000 rows depending on payload size.

## 10. Deletion and retention

- Removing an asset initially moves it to application trash.
- Purge is explicit and records an audit event.
- Managed originals are deleted only during purge and only after database intent is durably recorded.
- Linked originals are never deleted by catalog purge unless a separately designed feature is approved.
- Dependent derived artifacts are deleted asynchronously and remain rebuildable.

## 11. Backup and restore

A consistent backup includes:

1. SQLite online backup output;
2. `library.json`;
3. managed originals and application-owned sidecars;
4. optional derivatives and indexes, clearly marked as rebuildable;
5. taxonomy and model manifests sufficient to identify dependencies.

Backup validation checks database integrity, manifest checksums, and expected file counts. Restore never overwrites an existing library without explicit confirmation outside the design scope of automated operations.

## 12. Integrity maintenance

Maintenance commands include:

- SQLite quick and full integrity checks;
- foreign key checks;
- orphan file and derivative detection;
- hash verification sampling or full verification;
- FTS parity rebuild;
- taxonomy closure verification;
- vector index manifest verification;
- vacuum and analyze under controlled conditions.

## 13. Database decisions

### DB-001: Integer internal keys plus UUID public IDs

Balances SQLite performance with stable external identity.

### DB-002: Original and derived binaries outside SQLite

Avoids database bloat and simplifies media streaming and recovery.

### DB-003: AI suggestions are immutable provenance records

Review changes status and creates user domain data; it does not erase inference history.

### DB-004: Embeddings authoritative in SQLite, ANN index rebuildable

Prevents an opaque external index from becoming the only copy of model output.

### DB-005: Versioned query AST

Prevents saved searches from depending on schema-specific SQL.

## Resumable export journal (migration 011)

`export_plans` is the durable header for restart-safe export execution. It stores the immutable canonical plan JSON, destination, lifecycle state, completion metadata, manifest identity, and bounded terminal error text. Reusing a public plan identity with different canonical content is rejected.

`export_plan_items` stores deterministic output assignments and source identity before copying begins. Each row records source path, authoritative size and optional SHA-256, relative output path, stable item order, attempt count, lifecycle state, verified output size and SHA-256, and bounded error text. The unique plan/path constraint prevents two assets from publishing the same output name.

Only short state transitions use SQLite write transactions. File copying and hashing occur outside database transactions. On worker interruption, `running` items are reset to `pending`. A resumed execution validates every `succeeded` output by size and SHA-256; valid outputs are skipped and invalid outputs are returned to the retry path. Failed items are retried only on a subsequent explicit execution. The final manifest is produced only when every item is verified as succeeded.

## Migration 012 — resumable derivative exports

Migration 012 rebuilds the Milestone 10 export journal tables to widen `export_kind` from original-only plans to `original_files` and `derivatives` while preserving all existing plan and item rows. Derivative item rows add an immutable JSON metadata snapshot, rendered pixel dimensions, XMP path, XMP size, and XMP checksum. The rebuild is required because SQLite cannot alter an existing `CHECK` constraint in place.

## Migration 013 — regional knowledge
Adds `regional_profiles` and `regional_profile_countries`. Occurrence facts continue to live in `taxon_regions`; the profile only stores user priorities and display preferences.

## Migration 014: Observation Intelligence

`observation_assets` links one or more assets to a stable observation. Existing `observations.asset_id` remains as the legacy primary asset for compatibility; migration 014 backfills the join table and adds confirmed-taxon indexes.

## Migration 015 — Ecological context

`ecological_context` stores optional conservation status, seasonal months, migration status, habitats, and source attribution for installed taxa. The table is additive and does not alter taxonomy or observation records.

## Version 2 observation context

Migration `v017_observation_context` adds optional explicit observation context to `observations`:

- `observed_at_us` overrides the time derived from evidence assets.
- `location_id` links an observation directly to `locations`.
- `time_source` and `location_source` record provenance.
- `location_accuracy_m` records coordinate accuracy.

Existing observations remain valid. When explicit values are absent, queries continue deriving time and location from linked evidence assets.

Imported EXIF GPS coordinates are normalized into `locations` and linked to the asset with the `capture` role. Raw metadata remains preserved in the metadata snapshot.

## Version 2 spatial and longitudinal foundation (`v018`)

Migration `v018_spatial_longitudinal` adds map-ready and longitudinal structures without changing Version 1 asset or observation records:

- `monitoring_projects` organizes surveys and long-running studies.
- `monitoring_sites` gives meaningful names and optional boundaries to recurring field locations.
- `spatial_regions` stores bounding metadata plus validated JSON geometry for areas, site boundaries, surveys, and saved map selections.
- `observation_series` groups recurring observations of organisms, populations, sites, or phenological events.
- `observation_relationships` records typed links such as revisit, follow-up, same organism, same population, and comparison.
- link tables associate observations with multiple projects and sites while preserving the existing observation row.
- `map_bookmarks` stores offline-map viewpoints and optional saved filter JSON.

Spatial queries use explicit observation locations first and otherwise fall back to linked evidence-asset locations. Map-provider and tile-package concerns remain outside the library schema; offline map packages will be application-managed shared resources.

### Offline map package lifecycle

The `maps.offline` database owns package activation and verification state. Declared package checksums are retained as installation expectations; observed SHA-256 values are stored separately during verification. Coverage queries return only enabled packages in the installed state. Missing or invalid packages remain cataloged for repair and do not affect core-library availability.

### Lightweight OpenStreetMap offline packages

The optional `maps.offline` database supports OSM-derived raster MBTiles
packages through provider key `openstreetmap.mbtiles`. Package records retain
tile scheme (`tms` or `xyz`), data licence, attribution text, attribution URL,
coverage, zoom limits, package checksum, and verification state. Tile bytes
remain inside the external MBTiles package and are never copied into the core
Aperture Library.

## Temporal and movement foundation (schema v019)

`observation_series` now records subject type, optional subject identifier, identity confidence, tracking method, and connection policy. Series membership records may carry their own confidence, verification state, and tracking timestamp. `movement_segments` stores only user-verified or annotated segments; ordinary playback lines are derived from ordered series members. This prevents independent sightings from being misrepresented as a single animal's route.

## Taxonomy reference subsystem (`taxonomy-reference.sqlite3`)

This optional shared database is created only when taxonomy reference functionality is activated. Schema version 1 contains versioned datasets, accepted and synonym taxa, multilingual names, sourced knowledge facts, regional occurrence records, and external references. It is application-managed and is not part of an individual Aperture Library.

The existing Version 1 taxonomy tables in `library.sqlite3` remain valid during the transition. The core library continues to own observation assignments and stable public identifiers. No cross-database foreign keys are used.

### Taxonomy subsystem schema v002

`library_taxon_links` records optional mappings between an Aperture Library taxon and a shared reference taxon. Each record is scoped by `library_public_id` and stores only stable public IDs, link state, source, timestamp, and notes. It is not a foreign-key relationship to the core library and contains no copied observation data.

### Taxonomy subsystem schema v003

Taxonomy migration v003 adds authoritative package provenance and AI label mappings. Dataset records now retain licence URL, redistribution permission, source URL, and package schema version. Common names can retain source record identity and verification state. `ai_taxon_label_mappings` maps a model-family/version/label tuple to a stable reference taxon public ID without changing the original AI result.

### Taxonomy reference schema v004

The optional `taxonomy.reference` database stores one row of display preferences (`language_tag`, `region_code`, and common-name preference) and an independent enabled state for each installed dataset. These values affect read-time presentation only. Scientific identities, observations, and package contents are not rewritten.

## Schema v020 — Asset analyses

Version 2 schema migration `v020_asset_analyses` adds immutable, asset-linked enrichment records:

- `asset_analyses` — one versioned engine execution for one photo or other asset;
- `analysis_taxon_candidates` — ranked taxonomic hypotheses from that execution;
- `analysis_tags` — namespaced lightweight enrichment;
- `analysis_observation_promotions` — explicit links from analysis evidence to authoritative observations.

`ai_suggestions.analysis_id` optionally links the established AI review workflow to its parent analysis. Existing suggestions remain valid when no parent analysis is available.

The core library retains compact results and provenance. Embeddings, large masks, tensors, and model caches remain optional and rebuildable.

## Version 2 asset removal

Schema migration `v021_asset_removal` makes purge audit records independent of the asset row so an irreversible deletion can retain its outcome after the asset is gone.

Permanent deletion is analysis-aware. The application first produces a dependency preview. For an unlinked trashed asset, deleting the `assets` row cascades through asset-owned file instances, derivative manifests, embeddings, AI suggestions, immutable asset analyses, candidates, and tags. Confirmed observations and analysis promotions require an explicit unlink or delete policy before the asset can be removed.


## Offline map acquisition

Offline map package catalogs are external metadata, while installed package records remain in `maps-offline.sqlite3`. Downloaded MBTiles files live in the application-managed offline-map directory and may be removed without changing authoritative coordinates or observations.


## RC2.2
Production database remains isolated until atomic publish. Checkpoints never modify production tables.


## ADR: Offline map databases are independent resources

Each rendered region is an independent vector MBTiles SQLite database. Aperture stores only catalog metadata in its map subsystem database. Runtime tile reads open the regional database read-only; conversion, indexing, validation, and replacement occur outside the operational database. The downloaded OSM PBF remains a retained source and a replacement `.next.mbtiles` is published only after validation.

## Release 3 media and integration foundation

Migration 25 introduces:

- `library_capabilities`, with photographs, sounds, videos, and documents enabled by default;
- `library_assets`, the shared identity layer for all media;
- dedicated `photo_assets`, `sound_assets`, `video_assets`, and `document_assets` tables;
- `integration_systems` and `integration_capabilities`, the Aperture-owned integration control plane;
- compatibility migration of existing RC1 photographs into the new shared catalog.

Canonical enrichment is stored separately in `subsystems/enrichment.sqlite3`. Its stable envelope, typed values, namespaced labels, lifecycle status, and producer provenance remain usable without the producing integration.

> Release 3 implementation scope: no legacy-library data migration or compatibility backfill is included unless separately approved. The new structures are created for fresh Release 3 data while existing RC1 functions continue through their existing repositories.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.
## Excalidraw whiteboards

Fieldora 0.09.7 adds no whiteboard schema. Active whiteboards are Documents
files with document-owned snapshots. Existing Science whiteboard tables remain
unchanged as inactive compatibility state; no migration or automatic
conversion is performed.
