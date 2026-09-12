# Fieldora development

## Change direction

Fieldora development proceeds from domain invariants outward:

1. define or preserve the domain rule;
2. implement application services and repository contracts;
3. implement governed API behavior where applicable;
4. connect desktop and web adapters;
5. certify the behavior with focused tests and deployment checks.

Do not create separate desktop and web business rules for the same concept.

## Module boundaries

Keep ownership explicit. A module may reference another module through stable identifiers and services without taking ownership of its data. Avoid direct cross-subsystem table access, hidden shared persistence, and transactions spanning independent authorities.

## Persistence changes

Persistence work must define transaction boundaries, conflict behavior, migration behavior, backup/recovery impact, and parity expectations between SQLite and PostgreSQL adapters where both exist.

## Security changes

Server mutations and reads must preserve authentication, organization isolation, PBAC, and fail-closed behavior. Infrastructure changes must preserve service identity, secret boundaries, TLS/mTLS requirements, and least authority.

## UI changes

Desktop and web interfaces may differ in navigation and interaction, but domain validation and lifecycle rules belong below the UI. Browser JavaScript and Qt widgets should not be the sole location of a rule that affects persisted meaning.

## Testing and certification

Prefer small independently certifiable slices. The repository contains targeted GitHub Actions workflows for domain parity, API behavior, Docker installation, runtime security, storage, offline operation, Kubernetes infrastructure, and cross-module integration.

A green focused workflow is evidence for the contract it names; it is not a substitute for unrelated test coverage. When modifying a certified boundary, update its tests/workflow in the same change.

## Documentation

Update the current documentation entry point whenever a change alters architecture, security, installation, data ownership, or operator behavior. Preserve old release/audit evidence under historical documentation rather than mixing it into current procedures.

## Repository organization

- `src/natureai_next/` — implementation.
- `tests/` — automated behavioral and contract tests.
- `.github/workflows/` — certification workflows.
- `scripts/` — development, release, maintenance, and operational tooling.
- `deployment/` — deployable infrastructure assets.
- `docs/` — canonical current documentation and archived evidence.

Installer scripts remain at their current certified repository paths until a dedicated relocation change updates every workflow, raw-GitHub reference, helper-script reference, and operator instruction atomically.

## Pull requests

Use narrow branches and reviewable commits. Do not merge architectural cleanup together with unrelated product changes. For high-impact repository moves, preserve compatibility or update all consumers in the same PR.
