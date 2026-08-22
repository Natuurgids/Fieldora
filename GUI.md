
## Export and Reporting navigation

The navigation tree contains separate **Export** and **Reporting** groups. Export contains Export Assets and Export Data. Reporting contains Reports, Templates, Report History, and Statistics. File → Export uses Ctrl+E; File → Reporting uses Ctrl+Shift+E.

## Continuous OSM map

Area **All** renders every enabled downloaded OpenStreetMap extract through one merged vector source at the active zoom. Named areas remain available for navigation and filtering, but package boundaries are not visible in normal map use.
## Release 3 Reporting and Export placement

The application shell adds a top-level **Reporting** workspace for reports, templates, history, and export profiles. **Generate Report** is also available contextually from Observations, Photos, Sounds, Videos, Documents, and collection screens. The Export command group contains **Export Assets**, **Export Data**, and **Generate Report**. Report content and inclusion of original media are separate explicit choices, with a preflight summary of estimated size and unavailable originals.

## Aperture V3.RC1F1 AI resource status

AI Resources and Maintenance Center report separate readiness for model, execution variant, Tree-of-Life classifier resources, optional prompt sets, and GBIF. Analyse actions remain unavailable when the selected inference path is incomplete.

## AI Review single-photograph workflow (0.15.2)

AI Review includes a **Current photograph only** toggle. **Accept & Reject Rest** accepts the selected taxonomy and rejects every remaining pending/deferred alternative for that photograph. **Reject Other Options** can be used after a normal acceptance.

# NatureAI Next — GUI Design

**Status:** Approved design baseline  
**Document version:** 0.1

## 1. GUI goals

The PySide6 interface must feel like a native, high-performance Windows desktop application for large photo libraries. It must remain responsive during import, indexing, thumbnail generation, and AI inference.

The GUI is a presentation layer. It consumes application services and observable read models; it does not contain persistence, filesystem, or inference logic.

## 2. Interaction principles

- Preserve context and selection during background refreshes.
- Prefer non-modal workflows; reserve modal dialogs for destructive confirmation and short configuration tasks.
- Support keyboard-first operation for rating, tagging, navigation, and review.
- Show progress without blocking unrelated work.
- Use optimistic visual updates only when rollback is defined.
- Expose AI provenance and uncertainty.
- Never hide failures; summarize them with actionable detail.
- Scale correctly on high-DPI displays and multi-monitor setups.

## 3. Application shell

The main window contains:

1. **Title and command area** — current library, global commands, search entry, activity indicator.
2. **Navigation rail** — Library, Imports, Collections, Taxonomy, AI Review, Jobs, and Settings.
3. **Workspace area** — central routed content.
4. **Inspector panel** — contextual metadata and actions.
5. **Status bar** — selection count, result count, active sort/filter, background status, and offline/update state.

Panels may be resized and selected panels may be hidden. Layout is persisted per library and validated against current screen geometry at startup.

## 4. Workspaces

### 4.1 Library workspace

Primary photo management view:

- virtualized thumbnail grid;
- optional compact list view;
- filter bar;
- sort controls;
- saved-search access;
- breadcrumb/context header;
- multi-selection;
- inspector integration.

Visible thumbnails load asynchronously. The view requests bounded pages through a query service using keyset pagination.

### 4.2 Viewer workspace

Single-image and comparison viewing:

- fit, 100%, and custom zoom;
- pan and smooth zoom;
- orientation-correct display;
- optional before/alternate comparison;
- metadata overlay;
- region-of-interest drawing and editing;
- next/previous navigation respecting current result order.

Full-resolution decoding is tiled or bounded where image size requires it. Viewer transitions never block on AI work.

### 4.3 Import workspace

Import flow:

1. choose sources and storage policy;
2. scan and summarize candidates;
3. review duplicate and conflict policy;
4. start resumable import job;
5. inspect successes, skips, and failures.

The import plan is saved before execution. Closing the window does not cancel the job unless explicitly requested.

### 4.4 AI Review workspace

- queue grouped by suggestion type and model;
- image/crop preview;
- ranked candidates;
- taxonomy context;
- score type and provenance;
- accept, reject, defer, and choose-other actions;
- batch review with safeguards;
- keyboard shortcuts;
- filters for model, group, score band, and status.

Batch acceptance requires consistent target fields and displays the number of affected assets.

### 4.5 Taxonomy workspace

- hierarchy browser;
- scientific and vernacular name search;
- synonyms and accepted-name relationships;
- regional status;
- source and release metadata;
- linked asset counts;
- user taxa and mapping tools.

Taxonomy browsing uses lazy child loading and cached read models.

### 4.6 Collections workspace

- manual collections;
- smart collections defined by the visual query builder;
- collection hierarchy or grouping;
- drag/drop manual membership;
- saved sort and view state.

### 4.7 Jobs workspace

- active, queued, completed, and failed jobs;
- progress and throughput;
- pause/cancel/retry where supported;
- per-item failure drill-down;
- technical details copy/export;
- resource use summary.

### 4.8 Settings workspace

Separates:

- application settings;
- library settings;
- AI and model settings;
- storage and cache settings;
- plugin management;
- update settings;
- diagnostics.

Changes show whether they apply immediately, require model reload, require library reopen, or require application restart.

## 5. Inspector design

Inspector sections:

- file and capture information;
- rating, pick state, and color label;
- title, caption, and notes;
- tags;
- observations and taxonomy;
- location;
- AI suggestions and provenance;
- history/audit summary.

Sections are collapsible. Multi-selection displays common values, mixed-state indicators, and batch-edit semantics.

Edits use a draft buffer. Committing creates one application command; cancelling restores the persisted state. Autosave may be used only for low-risk scalar fields and must preserve undo grouping.

## 6. Search UX

### 6.1 Global search

The search entry supports plain text and recognized field syntax. Suggestions are generated locally from tags, taxa, places, and saved searches.

### 6.2 Visual query builder

Users can build nested AND/OR/NOT groups using supported fields. The UI serializes the versioned query AST defined in `DATABASE.md`.

### 6.3 Similarity search

Accessible from an asset, crop, text prompt, or selection. The UI clearly displays the active model and allows structured filters to refine results.

## 7. View-model architecture

Presentation logic uses view models or presenters with:

- immutable state snapshots;
- explicit commands;
- loading, empty, success, partial-failure, and failure states;
- cancellation of obsolete requests;
- selection identity based on asset public IDs;
- no direct SQL or model-provider calls.

Qt models implement incremental loading and role-based data access. Large result sets are not materialized as Python object graphs.

## 8. Threading rules

- All QWidget and Qt GUI object access occurs on the UI thread.
- Application work executes through services and job dispatchers.
- Results return via queued signals or a dedicated UI dispatcher.
- Signal payloads use immutable IDs and data objects, not live database connections or Torch tensors.
- Obsolete request results are discarded using request generations or cancellation tokens.

## 9. Thumbnail grid performance

- Virtualized item creation; no QWidget per thumbnail.
- Size-tiered cached thumbnails.
- Priority queue based on viewport proximity.
- Request coalescing for duplicate thumbnail keys.
- Memory cache bounded by bytes.
- Disk cache keyed by source content hash, renderer version, orientation, and requested tier.
- Placeholder rendering uses lightweight native painting.
- Rapid scrolling cancels or deprioritizes distant work.

## 10. Commands, shortcuts, and undo

Central command registry provides:

- stable command IDs;
- labels and icons;
- enabled/checked state;
- default shortcuts;
- menu, toolbar, context menu, and command-palette integration;
- plugin command registration.

Metadata edits that can be safely reversed participate in an application-level undo stack. Undo stores semantic inverse commands or audit-based patches, not widget snapshots. File imports, model installation, taxonomy activation, purge, and exports are not assumed undoable; they use explicit recovery or confirmation flows.

## 11. Dialog and notification policy

- Toasts for transient success and non-critical information.
- Inline banners for workspace-scoped warnings.
- Job center for long operations.
- Modal confirmation only for destructive or security-sensitive actions.
- Error dialogs include a stable error code and “copy technical details” option.
- Repeated errors are grouped to avoid notification storms.

## 12. Accessibility

- Logical tab order.
- Accessible names, descriptions, and states.
- Keyboard alternatives for drag/drop.
- No meaning conveyed by color alone.
- Minimum practical hit targets.
- Respect Windows text scaling and contrast settings where Qt supports them.
- Screen-reader testing for primary workflows before stable release.

## 13. Localization

All UI strings use translation catalogs. Dates, numbers, units, and plural forms use locale-aware formatting. Scientific names preserve canonical formatting independent of locale.

No concatenated translatable sentence fragments are allowed.

## 14. Visual design system

A small internal design system defines:

- spacing scale;
- typography roles;
- icon sizes;
- elevation/border usage;
- semantic states;
- focus indicators;
- thumbnail selection and rating overlays.

The application supports system-aware light and dark themes. Theme resources are centralized; feature widgets do not hard-code colors.

## 15. Window and session state

Persisted state includes:

- window geometry and state;
- panel sizes and visibility;
- active workspace;
- library view mode and thumbnail size;
- last non-sensitive search context;
- column widths;
- optional viewer zoom policy.

State is schema-versioned and sanitized when monitors or DPI change.

## 16. GUI testing

- view-model unit tests;
- Qt model contract tests;
- keyboard navigation tests;
- high-DPI layout smoke tests;
- selection preservation tests;
- stale async result tests;
- thumbnail scrolling benchmarks;
- screenshot-based visual regression for controlled components where stable;
- end-to-end workflow tests late in the roadmap.

## 17. GUI decisions

### GUI-001: Model/view grid, not widget-per-item

Required for 100,000-asset scalability.

### GUI-002: Job center instead of blocking progress dialogs

Allows continued work and durable progress.

### GUI-003: Draft-and-commit inspector edits

Creates predictable transactions and undo behavior.

### GUI-004: Central command registry

Keeps shortcuts, menus, context actions, and plugins consistent.

### GUI-005: AI review is a dedicated workflow

Prevents suggestions from being mistaken for confirmed metadata.

## Persistent catalog derivatives — 0.11.0

Library grid thumbnails and larger catalog previews are rendered asynchronously and cached in separate library directories. Grid items display a standard file placeholder while work is pending, a warning icon when rendering fails, and support explicit retry. Widgets never open database connections and never write cache files directly.

## Implemented full-image viewer (0.11.2)

The Library workspace opens a modeless viewer from an explicit button or tile double-click. The viewer receives only catalog and preview service ports. Catalog detail and preview bytes are loaded on retained worker threads, and request generations reject stale results during rapid navigation. `QGraphicsView` provides bounded cursor-anchored zoom and drag panning. Fit, actual-size, First/Last, Previous/Next, mouse, and keyboard controls are available. The ordering is the bounded set currently materialized in the Library workspace; loading additional catalog pages expands that ordering.

## Library quick search — 0.11.5

The Library header contains a clearable quick-search field. Input is debounced for 300 ms and Enter can submit immediately. Search runs on a worker thread and displays a result count. Empty input restores normal Library paging. Requests carry monotonically increasing identities so an older result cannot replace a newer query. Filtered rows retain thumbnails, metadata editing, selection, and Viewer launch behavior.


## Structured Library filters — 0.11.6

The Library workspace exposes a structured-filter panel for minimum rating, color label, pick state, inclusive capture-date bounds, minimum pixel dimensions, exact tags, and confirmed taxonomy names. Filters and Quick Search are combined by the application search service into one validated structured query and execute on retained worker threads. The Qt layer never compiles SQL. Clearing filters restores ordinary catalog paging without changing source files or catalog metadata.

## Capture-date filtering — 0.11.7

The Library From/To controls submit inclusive ISO calendar dates. They match either authoritative UTC capture timestamps or normalized EXIF local capture-date text.

## Saved searches and collections

The Library workspace provides a Saved views and collections panel. Users can save the active Quick Search and structured filters, reopen or delete saved searches, create manual collections, add the current multi-selection, open collections as live Library views, and return to the full Library. All persistence operations execute off the Qt UI thread.

## Collection management (0.12.1)
The Library workspace distinguishes manual and smart collections. Users can create smart collections from the current query, rename collections, edit descriptions, delete collections, and remove selected members from manual collections.


## Core pane docking policy (0.12.9)

Navigation and Inspector are deterministic core panes. Navigation is docked left and Inspector right. They may be hidden and restored through the View menu, but are not floatable top-level windows. Qt dock-state blobs are not persisted; window geometry, workspace, inspector visibility, sorting, and thumbnail size remain session settings.

## AI Review desktop workspace (0.13.0)

The Navigation rail's AI Review entry opens the production review queue. The workspace contains model and prompt status, queue counts, review-state and confidence filters, bounded Load more paging, suggestion details, provenance, and Accept/Reject/Defer/Reverse actions. Keyboard commands remain A, R, D, Ctrl+Z, J, and K. AI evidence is never presented as confirmed metadata until accepted.


## AI Review generation controls (0.13.2)

AI Review provides **Generate selected**, progress, and cancellation controls. Selection originates in the Library workspace and is passed by stable asset public ID. Generation runs outside the Qt UI thread. NatureAI blocks application shutdown while generation is active to protect Qt object ownership and inference-run integrity.

## AI resources dialog

AI Review exposes **Manage local AI resources…**. The dialog selects local package files, validates trusted Ed25519 public keys, installs and activates resources, and explicitly builds taxonomy text embeddings. Operations display actionable errors and never download data automatically.

## Regional knowledge setup
Open AI Review → Manage local AI resources → Regional knowledge setup. Select a continent, optional countries, preferred languages, and whether worldwide fallback remains enabled.

## Regional knowledge acquisition
The Regional Knowledge dialog provides **Save and download regional knowledge**. Progress covers discovery, taxonomy retrieval, package signing/install, prompts, and embeddings. Paths and trusted keys are derived from the configured NatureAI model workspace.


## Observation History workspace (0.15.3)
The Observation History workspace groups confirmed species, chronological observations, and all linked evidence photographs. Evidence thumbnails open in the standard Viewer. AI Review can navigate directly to the selected taxon.


## Life Lists & Statistics

The Observation Intelligence area includes a projection-based dashboard with personal species totals, observation and evidence counts, country coverage, first observations for the current year, biological-group life lists, and the most frequently observed species. All values are derived from confirmed observations and update without a separate synchronization step.

## Conservation & Seasonality workspace

The workspace imports a source-attributed ecological-context CSV. Matching scientific names update local taxon context; unknown names are skipped. AI Review displays the installed context in a separate evidence section.

## Version 2 offline Map workspace

The desktop navigation includes a **Map** workspace. Opening it activates the optional `maps.offline` subsystem on demand. The first lightweight implementation renders a local 3×3 raster-tile viewport from an enabled OpenStreetMap-compatible MBTiles package, supports pan and zoom, overlays observation and monitoring-site markers, and displays package attribution below the map at all times.

When no valid package covers the viewport, Aperture preserves the spatial overlays and reports that offline map coverage is unavailable. Map-package or optional-database failures do not prevent the library or other workspaces from opening.

### Knowledge Center workspace

The Taxonomy navigation entry lazily opens the Knowledge Center. Searching activates the optional taxonomy reference subsystem, displays reference facts and distribution data, and synthesizes local observation statistics from the active library. Observation History can open the corresponding Knowledge Center page; locally observed pages can return to the evidence timeline.

### Knowledge Center name preferences

The Knowledge Center can prioritize common names by language and region while continuing to show the accepted Latin scientific name. Changing these preferences reorders names at read time and does not modify taxonomy packages or observation records.

## Asset removal and enrichment cleanup — Version 2 M5.4

The Library workspace supports multi-selection removal through two separate actions. **Move to Trash** is reversible and retains files, thumbnails, analyses, suggestions, and observation evidence. **Permanently delete** is available only for items already in Trash and first displays a dependency summary covering managed files, cached derivatives, AI enrichment, active jobs, and linked observations.

When selected photographs support authoritative observations, Aperture requires an explicit choice to keep the observations while unlinking the photographs, delete both photographs and observations, or cancel. The default service policy remains blocking. Database and filesystem cleanup runs outside the Qt UI thread, and the Library refreshes only after the operation completes.

## Version 2 M5.6 knowledge projections

The Knowledge Center displays an explainable evidence summary supplied by the Knowledge Engine, including confirmed observations, evidence photographs, geographic coverage, and a normalized evidence score. The offline Map obtains observation overlays from the Knowledge Engine while local tiles and attribution remain the responsibility of the offline-map service.

## Version 2 M5.7 workspace integration

Observation History now receives species lists, observation histories, and related-taxon projections through the Knowledge Engine. AI Review receives personal observation context and the selected photograph's complete analysis history through the Knowledge Engine. The existing suggestion review controls remain unchanged.

## Version 2 Maintenance Center integration

The existing Maintenance Center remains the operational owner for Version 2. It now displays recent durable background work and uses the established job state transitions for **Pause Selected**, **Continue Selected**, and **Stop Selected**. The same center runs library and optional-subsystem health checks, backup and restore, bounded cleanup, and recovery-oriented diagnostics.

No second health application or workflow-control window is introduced. Optional map and taxonomy databases are inspected without being created or activated when they are unused.


## Offline map package manager

The existing Maintenance Center provides **Manage Offline Maps**. Users load a configured HTTPS or local JSON catalog, navigate continent/country/region/province levels, download or update province-level packages, enable or disable installed coverage, and remove packages to reclaim space.

## Version 2 Settings access

The desktop **Tools** menu exposes **Maintenance Center**, **Settings**, and **Help**. The navigation pane retains Settings as a grouped area and now includes a Settings landing page. The landing page shows the current library and links to AI Resources, Regional Knowledge, Health Check, Diagnostics, Updates, and Preferences.

## M6.9.6 Regional selection consistency

Offline Map setup now follows the same selection pattern as Regional Knowledge: users filter by continent and country, then tick one or more provider-defined province/state/region packages. Catalog URL or local catalog configuration is located under **Advanced map source** rather than being the primary interaction.


## M6.9.6 R3 resource navigation

The desktop navigation contains a **Resources** group for AI Resources, Regional Knowledge, Offline Maps, and Taxonomy Resources. These are separate capability-specific interfaces sharing only download verification, storage, and offline-state infrastructure. Offline Maps uses geographic package selection; Taxonomy Resources uses regional or authoritative taxonomy acquisition. Installed resources and cached catalogs remain visible offline.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.

## Build 3.322 Darwin Core source selection

Taxonomy Resources exposes separate actions for a GBIF Darwin Core ZIP and an already-extracted Darwin Core folder. Both routes use the same parser and reconciliation pipeline. Folder import avoids unnecessary archive handling and leaves the selected files untouched.

## Continuous offline map interaction

The raster map canvas displays adjacent downloaded map files as one geographic surface. Users can drag across package boundaries; releasing the drag recenters and loads the next surrounding tile window. The Area selector, Zoom to Area, arrow buttons, GPX overlays, temporal overlays, observations, assets, sites, and the existing vector renderer remain available.

## Export package options

Report and data export workflows may optionally include selected original photos, sounds, videos, and documents. The review step must show included, unavailable, excluded, and checksum-mismatched originals and offer Continue, Require all originals, or Exclude originals.

## Reporting workspace

The left navigation contains a top-level Reporting group with one Reporting workspace. It contains Export Assets, Export Data, and Generate Report tabs. File → Reporting and Export (Ctrl+E) opens the same workspace. Long-running work is queued in Activity Center and does not block navigation.

### All versus named map areas

**All** uses zoom-aware composite coverage. Below zoom 9, Aperture displays an installed country/global overview package; without one, it leaves the basemap empty and explains that an overview package is required rather than constructing a false map from unrelated provinces. At zoom 9 and above, intersecting regional packages can form continuous coverage. Selecting a named area remains a strict single-package view.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.

## Collapsible lower subject panel — requested UI enhancement

Photo and other subject workspaces that embed the shared lower visualization, canonical-enrichment, review, and provenance composition shall provide a user-controlled compact state. In the compact state, the lower composition is folded to approximately one header/status line so the primary photo or media area receives the released vertical space. Expanding restores the complete existing composition. Collapse and expansion are presentation-only actions: they shall preserve selection, scroll position, counts, review state, enrichment records, provenance, background work, and every existing command. The state participates in the normal persisted per-library layout. See `UI_COLLAPSIBLE_LOWER_PANEL_REQUIREMENT.md`.

## Document opening policy (Repair 19)

The Documents workspace renders PDF through Qt PDF and Markdown/plain text through `QTextBrowser`. Structured office formats are not converted or parsed inside Aperture. The workspace invokes the operating system's registered application using `QDesktopServices`; failure to resolve an application is reported with guidance to install a compatible office product. This keeps Aperture independent of Microsoft Office and LibreOffice while supporting their file formats as managed document assets.

## Build 27 navigation

The desktop shell groups pages by user task: Library, Library Management, Observations, Knowledge, Tools & Resources, and Settings. The File menu contains Import, Export, backup, restore, and Shutdown. About Aperture remains a separate top-level menu. Shutdown displays progress while Aperture completes its safe system-wide shutdown sequence.
## Excalidraw Whiteboards

Science → Excalidraw Whiteboards lists `.excalidraw` documents stored in
Documents/Whiteboards. The workspace can create, import, open, and snapshot
these documents and can open their containing folder. Opening uses the
full bundled Excalidraw application directly in Fieldora, including canvas
tools, text, shapes, images, libraries, undo/redo, zoom, and image export.
Changes autosave through the local Documents bridge. “Create document version”
writes an immutable checksum-named snapshot under the Documents area. The
former custom drawing canvas is not shown and existing legacy boards are not
migrated.
