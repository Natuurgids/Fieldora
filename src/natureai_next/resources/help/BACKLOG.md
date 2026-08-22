## Approved Reporting, Export, Backup, and Restore backlog

- Add the top-level Reporting workspace and contextual Generate Report commands.
- Implement aggregate observation reporting, including total-count-only output.
- Implement permission/export profiles and sensitive-field suppression.
- Implement selected original photo, sound, video, and document inclusion with missing-original manifests.
- Implement a central Aperture database inventory and coordinated SQLite snapshots.
- Extend backup/restore to all selected Aperture-owned subsystem databases.
- Add complete, active-type, and custom backup scopes; keep complete backup as the default.
- Exclude integration runtimes/caches such as BioCLIP while retaining accepted normalized enrichment.

# Aperture Backlog

## Approved for Release 3 planning

- Species Dashboard search and matching-photo overview.
- True higher-detail offline map tile generation beyond the Release 2 maximum zoom.
- Map rendering performance and system-resource utilization.
- Map maturity: globe-style navigation, rotation, coverage visualization, and richer interaction.
- Startup speed improvements based on measured startup phases.
- Platform progress standard: unrestricted internal updates, normally one UI presentation per second, independently throttled durable persistence.

## Build 6 — Workflow Completion usability

- Make Library search controls, results, empty states, filter feedback, saved searches, and view switching more approachable without changing query semantics.
- Improve grid, Viewer, Collections, and navigation presentation after field observation of the completed photography workflow.
- Keep natural-language assistance in Build 5 and semantic/similarity search in Build 8; do not pull either into general UI polish.

### Build 3 — Maps completion field gate

- The two field-reported entry-point/download bugs are implemented through one Bootstrap-composed workflow in the Builds 3.273–3.320 completion candidate.
- Remaining work is consolidated Windows field validation of acquisition, PMTiles creation, rendering, interaction, overlays, GPX, lifecycle, offline restart, CMD repair, and uninstall.
- Confirmed bugs are fixed immediately; improvements outside that complete Maps gate remain in the appropriate backlog.

## Explicitly not part of Aperture 2.0 RC1

The items above are approved future work and are not release blockers for RC1.

---

# Aperture and NatureAI_Next Backlog

## Purpose

This document records accepted work outside the Version 1 feature freeze. A backlog item does not enter implementation automatically. It must be assigned to a release, reviewed for data migration, accessibility, licensing, performance, and rollback impact, and approved before development.

The full directional plan is available in [ROADMAP.md](ROADMAP.md) and in **Help → Roadmap & Future Releases**.

## Version 2 — accepted priorities

### Taxonomy & Knowledge Center

Expanded taxonomy overview, hierarchy, synonyms, common names, revision history, identification guidance, ecology, distribution, conservation, reference media, observation analytics, AI information, Taxon Health, and taxonomy-maintenance tools.

### Content hashes and exact duplicates

Store SHA-256 during import, index it in SQLite, backfill existing libraries through Maintenance Center, detect exact duplicates, and support integrity verification. Perceptual duplicates remain later work.

### Import provenance and import sessions

Preserve original filename, original path, parent folder, source drive letter, source volume/disk/card name, volume identity where available, import session, timestamp, managed filename, and managed location.

### Dynamic AI orchestration

Keep BioCLIP while adding task-specific engines dynamically for classification, behavior, habitat, segmentation, quality assessment, OCR, and similarity as needed.

### Maintenance and migration

Cross-version database/library validation, migration reports, hash-index builder, backup verification, and an external Backup & Recovery utility capable of validating and upgrading restored libraries.

### AI workflow continuity

Offer a reminder for unfinished AI activities after confirming any required online capability.

### Deployment tooling

Develop the universal installer/update-release builder as a separate reusable project.

## Version 3 — accepted direction

Advanced analysis, multiple AI engines and ensembles, richer reports, collaboration, synchronization, shared taxonomy workflows, plugin growth, and perceptual duplicate review. Study suitable concepts from mature open-source digital asset managers such as digiKam while respecting licensing and maintaining an independent Aperture architecture.

## Version 4 — accepted direction

Offline maps, observation calendar, biological moments, monitoring projects, revisit suggestions, photo-completeness guidance, field packages, route support, and time-lapse planning/indication.

## Version 5 — accepted direction

Semantic and natural-language search, including visual/behavior queries such as “flying bird,” explainable results, similarity discovery, and dynamic use of the AI engines required for each query.

## Unassigned backlog

- broader Natuurgids visual design system and color coding after contrast/accessibility review;
- advanced export profiles;
- mobile/field companion options;
- additional metadata templates;
- expanded thumbnail failure diagnostics and decoder reporting;
- regional scientific data-exchange integrations.


## Map maturity (future release)

- Globe-style map navigation with rotation and graphical coverage selection.
- Visible installed-package boundaries and richer map styles.
- Multi-core tile preparation and adaptive rendering performance.


## Approved map-engine backlog (post-2.0)

- Seamless **Show all enabled offline maps** rendering across every installed MBTiles package.
- Calculate combined coverage bounds, support connected navigation and whole-world display when downloaded.
- Define deterministic overlap resolution, cache lookup order, world wrapping, and coverage indexing.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.

## Continuous map and export follow-up

- Add asynchronous raster tile prefetch and LRU cache metrics.
- Add optional downloaded-map boundary and package-name overlays.
- Connect report/data selection UI to `ExportPackagePlan`.
- Add destination-size estimation and removable-volume capacity checks.


## Dynamic model plugins (3.0.0rc1.post9)

Aperture now uses `resources/models.json` plus optional `aperture.models` entry points for model discovery. BioCLIP remains the default and keeps its existing runner/review path. New model inputs are declared as catalog parameters, outputs normalize into the canonical enrichment subsystem, and model runtime databases/caches remain disposable and excluded from authoritative backup. See `docs/DYNAMIC_MODEL_PLUGINS.md`.

### Collapsible lower enrichment/review panel

Add a shared expand/collapse affordance to Photos and every comparable subject workspace so the lower visualization, enrichment, review, and provenance composition can be reduced to one compact line. The released height must enlarge the primary media area. Treat this as a presentation-only change and preserve every currently functioning operation and all active workspace state. Acceptance details are recorded in `UI_COLLAPSIBLE_LOWER_PANEL_REQUIREMENT.md`.
