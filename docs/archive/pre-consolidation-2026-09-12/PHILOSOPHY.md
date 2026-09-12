# Aperture Development Philosophy

This document records the principles used when designing and extending Aperture.

## Product and engine boundary

Aperture owns the user experience, Aperture Library, data model, database formats, workspaces, and documentation. NatureAI Next is the integration engine that connects Aperture with external open-source technologies and future specialist components.

## Design principles

- Build for the individual user first.
- Keep ordinary use offline and local.
- Treat the user's Aperture Library as authoritative.
- Preserve photographs as evidence and allow multiple observations per photograph.
- Keep optional capabilities modular and lazily activated.
- Let each domain keep the interface and data model it actually needs.
- Share infrastructure only where it genuinely reduces duplication: verification, jobs, progress, storage, cleanup, and package lifecycle.
- Let AI assist without silently deciding.
- Make migration and compatibility part of feature design.
- Prefer lean dependencies and technologies that can be maintained over time.
- Separate authoritative data from rebuildable caches and derived artifacts.
- Document architecture and rationale so branches can evolve consciously rather than by reverse engineering.
- Keep future scientific contribution explicit, export-based, and voluntary.
- Give Science its own authoritative database and never hold a write transaction across
  Science and the personal media library.
- Link dossiers to media through stable public identifiers; never duplicate or mutate
  original evidence merely to organize a research project.

## Development workflow

Aperture follows: design, approve, build, test, analyse, fix, regress, document, package, field-validate, and freeze.

Build status is stated explicitly as Proposed, Approved, Implementation Prepared, Build Completed, Internal Validation Passed, Awaiting Field Validation, Field Validated, Corrective Build, or Frozen.


## Performance Principles
- Use available hardware efficiently.
- Memory for performance; storage for durability.
