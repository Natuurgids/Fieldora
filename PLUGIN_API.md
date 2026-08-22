# NatureAI Next — Plugin API

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. Purpose

The plugin API extends NatureAI Next without coupling the core to optional taxonomies, models, metadata formats, exporters, or specialized workflows.

Plugins are trusted local code and initially run in-process. They are not sandboxed. Installation UI and documentation must state that a plugin has the same operating-system access as the application.

## 2. Compatibility model

Three versions are distinct:

- application version;
- core plugin API version;
- plugin version.

The core plugin API follows semantic versioning:

- patch: compatible fixes and documentation;
- minor: backward-compatible additions;
- major: breaking contract changes.

A plugin manifest declares a supported API version range and minimum application version. Incompatible plugins are not imported.

Public plugin contracts live in a dedicated `natureai_next.plugin_api` package. Plugins must not import internal modules.

## 3. Discovery and packaging

Preferred packaging uses Python distributions with entry points under a NatureAI-specific group. Development plugins may be loaded from configured directories when developer mode is enabled.

A plugin distribution includes:

- Python package;
- manifest;
- license;
- optional resources;
- optional plugin database migrations;
- signature metadata for curated distribution.

Plugins are installed into an application-managed environment or approved plugin environment, not the base Miniconda environment of the developer.

## 4. Manifest

Required fields:

- stable reverse-domain plugin ID;
- display name;
- plugin semantic version;
- provider/author;
- description;
- license;
- supported plugin API range;
- minimum application version;
- capabilities requested;
- entry point;
- optional homepage and support metadata;
- optional package signature identity.

Capability declarations include filesystem access requirements, network requirement, UI contribution, model loading, taxonomy installation, and database storage.

Plugins requiring general network access are rejected for the standard offline product. Update-provider plugins may receive restricted update transport only when explicitly approved.

## 5. Lifecycle

1. discover package metadata without importing plugin code;
2. validate manifest and compatibility;
3. verify trust/signature policy;
4. resolve enabled state and capability grants;
5. import entry point;
6. call `register(context)`;
7. validate registrations;
8. activate after library open where required;
9. call `deactivate()` during disable or shutdown when safe.

Registration failures disable only the affected plugin and are logged. Core startup continues unless the plugin is explicitly required by the active library.

## 6. Plugin context

The registration context exposes narrow registries and services:

- API version and application metadata;
- command registry;
- panel registry;
- metadata reader registry;
- exporter registry;
- AI provider registry;
- taxonomy provider registry;
- job type registry;
- event subscription registry;
- plugin settings registry;
- namespaced data storage and migration service;
- structured logger;
- read-only capability and path information.

It does not expose raw service containers, arbitrary SQLite connections, or the main window object.

## 7. Extension points

### 7.1 Metadata reader

A metadata reader declares supported MIME types or file signatures and returns a normalized metadata result with:

- extracted fields;
- source/provenance;
- warnings;
- unrecognized raw fields where allowed;
- reader version.

Readers do not write to the database directly.

### 7.2 Exporter

An exporter receives an immutable export plan and controlled read interfaces. It writes only to the user-approved destination through a provided filesystem abstraction and returns itemized results.

### 7.3 AI provider

An AI plugin may register model families or execution providers that satisfy the AI ports and model manifest rules in `AI.md`. Provider output must be serializable and provenance-complete.

### 7.4 Taxonomy provider

A taxonomy provider validates and converts a package into the core taxonomy import format. It cannot mutate active taxonomy tables directly.

### 7.5 Job type

A job plugin declares payload version, resource class, recovery behavior, cancellation checkpoints, progress schema, and result schema. Execution receives bounded services and a plugin data namespace.

### 7.6 UI panel

A UI plugin may contribute:

- navigation workspace;
- inspector section;
- settings page;
- viewer overlay;
- context action.

UI contributions communicate with core through commands, queries, and approved read models. They may not issue SQL or access Torch models directly.

### 7.7 Commands

Commands have globally unique IDs prefixed by plugin ID. They declare label, description, icon resource, default shortcut, context predicate, and handler.

### 7.8 Event subscribers

Subscribers receive versioned public events after commit. Delivery is at least once; handlers must be idempotent. A failing subscriber is retried according to policy and may be disabled without rolling back the originating transaction.

## 8. Data access

### 8.1 Core data

Plugins access core data through documented read queries and application commands. Direct updates to core tables are prohibited.

### 8.2 Plugin data

Plugins may use:

- small namespaced key/value settings;
- namespaced relational tables created through plugin migrations;
- files under a plugin-specific data directory.

Plugin tables are prefixed `plugin_<normalized_plugin_id>__`.

### 8.3 Migrations

Plugin migrations are:

- numbered and immutable;
- checksummed;
- applied through the core migration service;
- limited to the plugin namespace;
- backed up according to library migration policy.

A disabled plugin's data remains unless the user explicitly removes it.

## 9. Filesystem access

Plugins receive paths or handles only for approved scopes:

- plugin package resources, read-only;
- plugin global data;
- plugin library data;
- user-approved export destination;
- source files through read-only asset access.

Plugins must not modify originals. Managed path internals are not stable API.

## 10. Network policy

The default plugin API provides no generic HTTP client. A plugin cannot claim standard compatibility if core functionality requires network access after installation.

Restricted update transport may be exposed only to plugin types that install model or taxonomy packages and only through explicit user-initiated update flows. Core transport enforces destination policy, timeout, size limit, integrity verification, and staging.

## 11. Threading and UI safety

- Plugin UI callbacks run on the Qt UI thread.
- Long work must be submitted as a job or asynchronous application task.
- Plugin code must not retain Qt objects across incompatible threads.
- Plugin background results return through core dispatchers.
- Plugins must respect cancellation tokens and bounded resource use.

## 12. Fault handling

The plugin manager tracks:

- load failure;
- registration failure;
- repeated command failure;
- job failure rate;
- event subscriber failure;
- incompatible API use.

A faulting plugin can be disabled for the current session. Failures include plugin ID and version in diagnostics. Core data transactions are protected by application service boundaries.

## 13. API stability rules

Stable API includes only symbols explicitly exported by `natureai_next.plugin_api`. Everything else is internal.

Contracts use:

- immutable dataclasses or equivalent models;
- enums with unknown-value handling where serialized;
- semantic identifiers rather than database row IDs;
- versioned event and job payloads;
- documented exception types.

Adding optional fields is backward-compatible when defaults are defined. Removing fields, changing semantics, or tightening accepted values requires a major API version.

## 14. Plugin testing

The project provides a plugin test kit containing:

- manifest validator;
- contract test suites;
- fake application context;
- temporary library fixture;
- event redelivery test;
- cancellation and recovery test helpers;
- UI-thread assertion helpers;
- compatibility report generator.

Curated plugins must pass the test kit and packaging validation.

## 15. Reference plugin categories

The repository may include maintained first-party plugins for:

- specialist taxonomy sources;
- additional AI model providers;
- metadata formats;
- export formats;
- offline maps or geographic layers;
- domain-specific review panels.

First-party plugins use the same public API as third-party plugins wherever practical.

## 16. Plugin decisions

### PL-001: Trusted in-process execution

Selected for performance and desktop integration. The product does not claim sandbox security.

### PL-002: No internal imports

Protects long-term compatibility and enables refactoring behind stable contracts.

### PL-003: No direct core database writes

Preserves invariants, auditing, migrations, and transaction ownership.

### PL-004: Network absent by default

Maintains the offline guarantee and makes network use auditable.

### PL-005: At-least-once event delivery

Works with the persisted outbox; plugin handlers must be idempotent.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.
