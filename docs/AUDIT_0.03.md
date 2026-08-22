# Fieldora 0.03 Architecture and Product Audit

## Executive result

**Overall: partially aligned; suitable as an early development release, not ready to
declare architecture-complete.**

The software strongly preserves offline operation, local ownership, immutable media,
modular AI, explicit review, and separate Science storage. The main risk is that the
new Science implementation is concentrated in one large Qt module and bypasses the
application/infrastructure boundaries required by the architecture and coding standard.

The reviewed tree contains 376 Python source files, 109 test modules, and approximately
329 test functions. Source compilation and targeted Science database tests pass in the
available environment. Full Ruff and pytest execution remains unavailable here.

## Alignment matrix

| Source | Status | Evidence | Gap |
| --- | --- | --- | --- |
| Vision: personal usefulness | Aligned | Library, observations, local AI, projects, dossiers | Science onboarding and dossier retrieval remain basic |
| Vision: offline first | Aligned | SQLite, local models, offline maps, no Science service dependency | Optional acquisition paths still require explicit network UX validation |
| Vision: user owns data | Aligned | User-selected library, local databases, export/backup architecture | `science.sqlite3` is not yet included in backup and health inventory |
| Vision: evidence preservation | Aligned | Dossiers reference stable media IDs without rewriting originals | Missing broken-link diagnostic for removed/unmounted media |
| Philosophy: modular domains | Partial | Dedicated Science database and cross-database IDs | Science UI directly owns SQL and persistence |
| Philosophy: AI assists | Aligned | Suggestions remain reviewable; YOLO-to-BioCLIP retains provenance | Pipeline requires broader runtime integration testing |
| Architecture: subsystem ownership | Partial | Science has its own database | No Science repository, service, migration module, or typed port |
| Architecture: no external servers | Aligned | Embedded SQLite and in-process Qt | None for current scope |
| Architecture: durable workflows | Partial | Existing durable job system is present | Science mutations and future long operations are not workflow-backed |
| Roadmap: stable foundation | Partial | Broad implemented surface and compatibility mechanisms | Product history still uses mixed legacy “Version 1/2/4” terminology |

## High-priority findings

### A-01 — Science database is absent from coordinated backup and health

Severity: high. `science.sqlite3` is authoritative Science data, but current backup and
Maintenance Center inventory were designed before it existed. A library backup can
therefore omit projects, dossiers, artifacts, activities, and whiteboard links.

Required action: register Science as an authoritative optional subsystem in backup,
restore, integrity checking, diagnostics, and storage inventory.

### A-02 — Science violates the UI/application/infrastructure boundary

Severity: high. `ui/qt/science.py` creates tables, runs SQL, performs migrations, applies
business rules, and renders widgets. This conflicts with the coding rule that subsystem
repositories own schemas and UI must not own persistence.

Required action: introduce `domain/science.py`, `application/science.py`, and
`infrastructure/database/science.py`; keep Qt limited to presentation and commands.

### A-03 — Science persistence rewrites complete tables

Severity: medium. Each edit deletes and reinserts cached projects, notes, activities,
artifacts, dossiers, and media links. A transaction prevents partial commits, but the
approach increases lock duration and makes concurrent/background Science work unsafe.

Required action: use incremental insert/update/delete commands with optimistic revisions.

### A-04 — Dossier lifecycle is incomplete

Severity: medium. Creation and linking work, but editing, deletion, search, media
availability diagnostics, artifact linking, and provenance history are incomplete.

Required action: add dossier detail, lifecycle state, revision, audit events, and
broken-link reporting.

### A-05 — Whiteboard persistence is incomplete

Severity: medium. Notes are durable, but moved coordinates are not written back after a
drag and “doodle” is currently textual rather than freehand/vector input.

Required action: persist geometry changes and add a compact vector-stroke representation.

### A-06 — Release terminology is inconsistent

Severity: medium. Current identity is Fieldora 0.03, while major documents still
describe historical Aperture Version 1, Version 2, and Version 4 milestones as if they
were the active release line.

Required action: retain history but label it as legacy platform history; use 0.x Science
milestones for current planning.

## Documentation cleanup completed

- Established `docs/DOCUMENTATION.md` as the canonical map.
- Moved build, phase, repair, and validation evidence into `docs/archive/`.
- Removed redundant authoring copies of Vision, Philosophy, and the Version 2 charter.
- Defined packaged Help as a generated mirror instead of an authoring location.
- Added this audit and a dedicated Science architecture document.

## Recommended release sequence

1. **0.04 — Science integrity:** repository/service extraction, schema migrations,
   incremental writes, backup/restore/health registration.
2. **0.05 — Dossier lifecycle:** edit/search/delete, artifact links, media diagnostics,
   revisions, and provenance.
3. **0.06 — Research canvas:** persistent note positions, vector doodles, and dossier
   canvas previews.
4. **0.07 — Scientific export:** documented, user-selected dossier/project packages with
   checksums and explicit media inclusion.

## Audit conclusion

The direction matches the Vision and Philosophy, especially local ownership and
optional Science. The architecture is not yet fully upheld because authoritative
Science persistence is implemented in the Qt layer and is not protected by coordinated
backup or health services. Those are release-blocking issues before Science data should
be described as production-safe.
