# Fieldora Documentation Map

This is the canonical documentation index for Fieldora.

## Product governance

- [`../VISION.md`](../VISION.md) — enduring product purpose and boundaries.
- [`../PHILOSOPHY.md`](../PHILOSOPHY.md) — development and design principles.
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — current system architecture.
- [`../ARCHITECTURE_DECISIONS.md`](../ARCHITECTURE_DECISIONS.md) — accepted decisions.
- [`../ROADMAP.md`](../ROADMAP.md) — future direction and delivery sequence.
- [`../CODING_STANDARD.md`](../CODING_STANDARD.md) — implementation rules.
- [`../DATABASE.md`](../DATABASE.md) — data ownership and schema overview.
- [`SCIENCE_ARCHITECTURE.md`](SCIENCE_ARCHITECTURE.md) — Science-specific boundaries.
- [`AUDIT_0.05.md`](AUDIT_0.05.md) — current Science persistence audit and freeze gate.
- [`PORTABLE_PROJECT_PACKAGES.md`](PORTABLE_PROJECT_PACKAGES.md) — offline project exchange format and limits.
- [`ACCESS_CONTROL_ARCHITECTURE.md`](ACCESS_CONTROL_ARCHITECTURE.md) — identity, contracts, PBAC decisions, and audit boundaries.
- [`SERVER_ARCHITECTURE.md`](SERVER_ARCHITECTURE.md) — reference server, session, API, web-client, and security boundaries.

## User, operator, and developer documentation

- [`getting-started/`](getting-started/) — installation and first use.
- [`user-guide/`](user-guide/) — feature guidance.
- [`operations/`](operations/) — backup, recovery, updates, and troubleshooting.
- [`developer/`](developer/) — implementation and release guidance.
- [`accessibility/`](accessibility/) — accessibility and keyboard operation.

## Generated runtime help

`src/natureai_next/resources/help/` is the packaged runtime mirror used by the
integrated Help browser. It is not a second authoring location. Run
`python scripts/sync_help_docs.py` after changing canonical documentation.

## Historical evidence

Historical build notes, repair reports, and validation snapshots are retained in
[`archive/`](archive/). They provide provenance but do not describe the current
product.

## Maintenance rules

1. Put current truth in one canonical document.
2. Link to canonical material rather than copying it.
3. Move superseded build evidence to `docs/archive/`.
4. Regenerate runtime help and the release manifest before packaging.
5. Record architecture deviations in the current audit until corrected.
