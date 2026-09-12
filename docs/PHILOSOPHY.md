# Fieldora philosophy

Fieldora is developed as an evidence platform, not as a collection of unrelated screens or deployment-specific products.

## Evidence and provenance before convenience

Original evidence must remain identifiable, traceable, and separate from interpretations and derived artifacts. Stable public identifiers are preferred over physical-file coupling. Organizing, linking, analysing, or sharing evidence must not silently mutate its origin or provenance.

## Domain semantics are authoritative

Business and scientific rules belong in domain and application layers. Desktop, web, API, CLI, persistence, and infrastructure adapters implement those rules; they do not define alternative versions of them.

A rule that exists only in browser JavaScript or only in a Qt widget is incomplete unless it is genuinely presentation-specific.

## One meaning across desktop and web

Desktop and web may present different workflows appropriate to their medium, but they must agree on object identity, validation, evidence ownership, provenance, deduplication, authorization, lifecycle, and scientific state transitions.

Parity means semantic equivalence, not pixel equivalence.

## Local usefulness first

Fieldora should remain useful on a personal computer without requiring continuous network access. Optional connected services may improve collaboration, acquisition, storage, mapping, taxonomy, or computation, but local evidence must not become unreadable because an external service is unavailable.

## The user controls evidence

Users and organizations decide where evidence is stored, how it is backed up, and what is exported or shared. A research module may reference Library evidence without assuming ownership of it.

## Explicit module ownership

Each module owns its records and invariants. Cross-module relationships use explicit contracts and stable IDs. Cross-database coupling, hidden shared tables, and transactions spanning independent authorities are avoided.

Shared infrastructure is appropriate for concerns such as jobs, verification, storage protocols, trust, progress, diagnostics, migrations, and package lifecycle—but shared infrastructure does not erase domain ownership.

## Default deny and least authority

Governed deployments fail closed. Identity, organization, policy, contracts, roles, attributes, and object grants contribute to a single authorization decision. Services receive only the credentials and trust material they need.

## AI assists; it does not become authority by accident

AI output is a suggestion or derived artifact until a governed workflow promotes it. AI must not silently replace user-confirmed facts, original evidence, or provenance.

## Authoritative data is distinct from rebuildable data

Caches, previews, indexes, thumbnails, search accelerators, and derived artifacts should be rebuildable where practical. Authoritative records, originals, governance history, and provenance receive stronger durability and migration guarantees.

## Compatibility is part of feature design

A feature that changes persisted meaning is incomplete without migration, compatibility, export, backup, and recovery considerations. Long-lived evidence matters more than a single software release.

## Small, certifiable changes

Development should proceed through narrow slices with explicit boundaries and focused tests. Architectural contracts are certified independently where possible. Broad refactors must not silently weaken module boundaries, security, or desktop/web parity.

## Open architecture

Architecture, rationale, and interfaces should be documented well enough that maintainers can understand why a boundary exists. Specialised deployments and future branches may evolve, but divergence should be deliberate rather than caused by undocumented coupling.
