# Aperture Product Roadmap

**Status:** Directional roadmap for post-Version 1 development  
**Scope:** Aperture product, NatureAI_Next engine, documentation, and supporting tools  
**Dates:** Deliberately not assigned. Priorities may change after field use and user feedback.

## Guiding principles

Aperture is designed as a long-lived, offline-capable scientific platform. Development follows these principles:

- Data integrity before convenience.
- Scientific accuracy before automation.
- Accessibility by design.
- AI assists expert judgement; it does not silently replace it.
- Libraries, observations, and provenance remain under user control.
- New AI models are modular and replaceable.
- Stable workflows and backward compatibility are preserved whenever practical.
- Major schema changes are introduced only in planned releases with migration and rollback support.

## Version 1 — Foundation Release

Version 1 establishes the stable Windows desktop platform:

- Aperture desktop application powered by the `NatureAI_Next` engine.
- BioCLIP-assisted identification and AI review workflows.
- Managed Aperture Library using SQLite.
- Import, catalog, observation, taxonomy, search, and export foundations.
- Pause, resume, cancel, and interrupted-job recovery.
- Accessible keyboard and screen-reader operation.
- Windows installer, repair, upgrade, and uninstall workflows.
- Maintenance Center, diagnostics, backup, restore, rollback, and recovery.
- Offline Help and operational documentation.

Version 1 is feature-frozen except for verified release blockers and data-safety defects.

## Version 2 — Knowledge and Library Management

Version 2 strengthens taxonomy, provenance, library integrity, and modular AI support.

### Taxonomy & Knowledge Center

- Expanded taxon overview, hierarchy, synonyms, common names, authorities, and identifiers.
- Taxonomic history, revisions, splits, merges, and source versioning.
- Identification characteristics and similar-species guidance.
- Ecology, habitat, phenology, behavior, host relationships, and conservation data.
- Reference media for life stages, sexes, seasons, structures, and habitats.
- Observation analytics and AI-related taxon information.
- Taxon completeness or “Taxon Health” dashboard.
- Taxonomy validation, import, merge, split, replacement, and index maintenance tools.

### Image provenance and import sessions

New imports will preserve source provenance, including:

- original filename;
- original full path and parent folder;
- source drive letter at import time;
- source volume label, disk/card name, and stable volume identifier when available;
- import session identifier and timestamp;
- managed-library filename and location;
- source and managed file diagnostics.

This supports dataset export, troubleshooting, chain-of-custody records, card/SSD import auditing, and future synchronization.

### Content hashes and duplicates

- Store SHA-256 once during import while the file is copied or read.
- Indexed exact-duplicate detection without repeated full-file hashing.
- Resumable hash backfill for existing libraries.
- Library and backup integrity verification.
- Exact duplicate review and safe storage policies.
- Perceptual duplicate detection remains a later feature.

### Dynamic AI orchestration begins

NatureAI_Next will evolve from a single-model integration into a modular orchestrator. BioCLIP remains an important engine, while additional task-specific models may be loaded only when required. Planned categories include taxonomy classification, behavior, habitat, segmentation, quality assessment, similarity, OCR, and future specialist engines.

### Workflow and maintenance

- Reminder for unfinished AI activities after an online-capability check where required.
- AI job history and improved progress reporting.
- Database migration assistant and cross-version library validation.
- Hash index builder, backup verification, and richer library diagnostics.
- Universal release/update builder work begins as a separate reusable project.

## Version 3 — Advanced Analysis and Collaboration

- Mature dynamic AI engine selection and model ensembles.
- Additional specialist AI engines alongside BioCLIP.
- Advanced scientific reports and export profiles.
- Multi-library synchronization and integrity comparison.
- Shared or collaborative taxonomy and research workflows.
- Plugin and extension growth.
- Visual similarity and perceptual duplicate review where scientifically appropriate.
- Lessons and suitable approaches may be studied from established open-source digital asset managers such as digiKam, subject to license compatibility and independent Aperture architecture decisions.

## Version 4 — Planning and Field Intelligence

Version 4 helps users decide what, where, and when to observe.

### Calendar and biological moments

- Observation calendar based on flowering, breeding, migration, emergence, fruiting, and other biological periods.
- Suggested observation windows by species, taxonomic group, project, region, or location.
- Monitoring reminders and overdue revisit indicators.

### Photo-completeness suggestions

Aperture may suggest evidence needed to improve an observation, such as:

- dorsal and ventral views;
- flower, leaf, fruit, bark, stem, cap, gills, base, or habitat views;
- juvenile, male, female, seasonal, or diagnostic structures;
- repeat photographs from the same position.

### Time-lapse and revisit planning

- Recommended revisit intervals.
- Same-location and same-viewpoint guidance.
- Seasonal and multi-year time-series projects.
- Time-lapse suitability and sequence-completeness indicators.

### Offline maps

Offline maps are planned for Version 4 because they are integral to field planning:

- offline regional map packages;
- observation, project, route, and monitoring-site overlays;
- clusters, density, distribution, and revisit status;
- topographic, conservation, and other licensed layers where available;
- GPX and field-package workflows;
- map and calendar integration for suggested field activities.

## Version 5 — Intelligent Search and Discovery

- Natural-language and semantic search such as “flying bird,” “butterfly feeding on flowers,” or “fungi on dead wood.”
- Behavior, posture, habitat, visual attribute, and ecological-context search.
- Similar-observation and visual-similarity discovery.
- Cross-project and, where enabled, cross-library discovery.
- Scientific compound queries combining taxonomy, time, location, behavior, and project data.
- Explainable matches showing why a result was returned and which engine or metadata contributed.
- Dynamic incorporation of the AI engines needed for each search task.

## Backlog and release assignment

Not every accepted idea is assigned immediately. Items remain in the backlog until dependencies, migration impact, licensing, accessibility, and validation requirements are understood. The roadmap describes direction rather than a delivery promise.

## Library compatibility commitment

Aperture treats the user’s library as the most valuable part of the system. Future releases will provide documented migrations, validation, backups, and rollback paths for schema or metadata changes whenever practical.
