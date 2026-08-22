# Aperture Version 2 Development Charter

## Baseline

Aperture 1.0.0 — Foundation Release is the authoritative baseline for all Version 2 development.
The exact source tree shipped with Version 1.0.0 must remain reproducible and maintainable on a
separate release line. Version 2 work starts from this baseline and must not silently rewrite or
invalidate Version 1 libraries.

## Product and engine identity

- **Product:** Aperture
- **Internal engine:** NatureAI_Next
- **Primary Version 1 vision model:** BioCLIP
- **Version 2 direction:** modular AI orchestration, richer taxonomy and knowledge, and stronger
  library provenance and integrity capabilities.

The existing package, environment, module, and engine names remain unchanged unless a separately
approved migration plan requires otherwise.

## Permanent engineering principles

1. Data integrity before convenience.
2. Scientific accuracy before automation.
3. Accessibility by design.
4. Offline-first operation wherever practical.
5. User ownership and portability of libraries and media.
6. Backward compatibility wherever practical.
7. Explicit, tested migrations for every schema or format change.
8. AI assists expert judgment and must remain transparent.
9. Root-cause fixes are preferred over symptom patches.
10. Real Windows acceptance testing complements automated regression tests.

## Branch and release policy

Recommended lines:

- `release/1.0`: Version 1 maintenance and critical fixes only.
- `develop/2.0`: Version 2 feature development.

Version 1 receives only critical reliability, security, compatibility, and data-safety corrections.
New capabilities belong to Version 2 or a later roadmap release.

## Version 2 priorities

### 1. Migration framework

Build and test a transactional database migration framework before introducing new schema fields.
Every migration must support validation, backup, rollback on failure, and clear diagnostics.

### 2. Import provenance and sessions

Preserve source information for each imported asset:

- original filename;
- original full path and parent folder;
- source drive letter at import;
- source volume label or disk/card name;
- source volume serial or stable identifier where available;
- import-session identifier and timestamp;
- managed filename and managed path.

Import Sessions must provide a permanent, queryable record of source media, imported counts,
failures, and future duplicate decisions.

### 3. Content hashing and exact duplicates

- Calculate SHA-256 once while importing or backfilling an asset.
- Store the hash in SQLite and index it.
- Never infer duplicates from filenames alone.
- Provide a resumable Maintenance Center task for existing assets without hashes.
- Do not delete or merge user data automatically.

### 4. Taxonomy & Knowledge Center

Expand the Version 1 Taxonomy Library into a curated knowledge system covering:

- hierarchy, accepted names, synonyms, authorities, common names and languages;
- taxonomic history and revisions;
- identification characteristics and similar species;
- habitat, ecology, phenology, distribution and conservation;
- references and media;
- observation analytics and AI-related quality information;
- a Taxon Health completeness dashboard;
- validation, import, merge and split workflows for authorized maintainers.

### 5. Modular AI orchestration

NatureAI_Next evolves into an orchestrator that can select appropriate engines for identification,
behaviour, habitat, segmentation, quality assessment, similarity, and future tasks. BioCLIP remains
an identified component rather than a generic unnamed AI engine.

### 6. Maintenance and integrity

Planned Version 2 maintenance capabilities include hash indexing, library verification, backup
verification, migration assistance, provenance diagnostics, and improved thumbnail-failure details.

## Later roadmap boundaries

- **Version 3 — Advanced Analysis & Collaboration:** additional AI engines, reporting,
  synchronization, scientific exchange and collaborative workflows.
- **Version 4 — Planning & Field Intelligence:** offline maps, biological calendar, monitoring
  projects, revisit suggestions, photograph-completeness guidance and time-lapse planning.
- **Version 5 — Intelligent Search & Discovery:** natural-language and semantic search, behaviour
  search such as “flying bird,” visual similarity and explainable result matching.

These directions are plans, not date commitments. Priorities may change based on real-world use,
but library integrity and compatibility remain governing principles.

## Development workflow

For each increment:

1. Define the user outcome and compatibility impact.
2. Identify schema, library-format and migration consequences.
3. Implement the smallest coherent change.
4. Add unit, contract, migration and integration coverage.
5. Build a complete Windows package.
6. Test on the real target environment.
7. Collect logs and reproduce failures.
8. Correct the root cause.
9. Run the complete regression and deployment preflight.
10. Update source documentation and packaged Help together.

## Acceptance requirements

No Version 2 feature is complete until:

- migrations and rollback paths are tested;
- existing Version 1 libraries remain readable or receive an explicit safe migration;
- accessibility behavior is verified;
- diagnostics identify failure stages;
- documentation and Help reflect the actual implementation;
- the release package manifest and checksum validate.

## Open-source reference policy

Projects such as digiKam may be studied for established approaches to metadata, collection scaling,
thumbnail databases, device import, maps, duplicate workflows and plugins. Source reuse must comply
with applicable licenses and be reviewed before incorporation. Aperture retains its own observation-
centred scientific architecture and product identity.
