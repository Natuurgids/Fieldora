# Desktop ↔ Web functional parity audit

This branch restarts the desktop-versus-web review from behavior, not from the current web implementation.

The Qt desktop application is the functional reference unless a server/domain contract or a documented security invariant intentionally differs. The existing web implementation is evidence, not the specification.

## Strategy

Do **not** rebuild the whole platform from zero. Preserve domain, persistence, security, audit, API and deployment behavior that is already correct. Rebuild or refactor the web presentation layer module-by-module when the audit shows that the current implementation is too coupled, implicit, or difficult to certify.

Each functional area is audited in this order:

1. Identify the desktop workflow and user-visible actions.
2. Identify the domain/application services it actually depends on.
3. Identify the corresponding web UI, API routes and browser wiring.
4. Record missing, partial, duplicated or behaviorally different functions.
5. Define an explicit web-module contract before changing implementation.
6. Classify the module as **keep**, **refactor**, or **rebuild**.
7. Implement one module at a time behind focused contract, API and browser tests.
8. Certify final-DOM action wiring so a visible control cannot ship without an owned action contract.

## Audit dimensions

Every function is compared across these dimensions:

- user intent and entry point;
- visible controls and keyboard/accessibility behavior;
- inputs and validation;
- outputs and user feedback;
- persisted state changes;
- domain/application service calls;
- API endpoints and request/response shapes;
- authorization/capability requirements;
- environment/runtime dependencies;
- asynchronous jobs and progress reporting;
- failure, retry and cancellation behavior;
- offline/network assumptions;
- audit/provenance effects;
- integration points with other modules;
- automated test coverage.

## Initial functional domains

The first-pass inventory is organized by behavior rather than source-file boundaries:

| Domain | Desktop reference areas | Web audit focus | Status |
| --- | --- | --- | --- |
| Identity & access | access control, login/session behavior | login, OIDC, capability projection, logout, PBAC visibility | Not audited |
| Home & activity | activity, activity calendar, application shell | home metrics, continue-work, status, recent activity | Not audited |
| Library & evidence | media/evidence workflows, bundle/import dialogs | evidence browse/detail, import files/folders, staged intake, linked archives | Not audited |
| Observations | observation editing and review workflows | list/detail, create/edit, accept/reject/defer, evidence linking | Not audited |
| Projects & portfolio | project/work hierarchy and planning | create/edit projects, phases/tasks, portfolio views, exports | Not audited |
| Capacity & availability | scheduling/capacity views | schedules, absences, allocations and availability records | Not audited |
| Research & dossiers | scientific records and dossier workflows | research records, dossiers, review state and relationships | Not audited |
| Knowledge & AI review | AI review, enrichment and synthesis workflows | analysis, proposal review, human/external identification | Not audited |
| AI resources & setup | AI resources, AI setup | providers, models, MCP/connectors and offline resources | Not audited |
| Administration & governance | administrative/security operations | users, roles, passwords, contracts, approvals, devices, audit | Not audited |
| Facilities & storage | facilities/location/storage workflows | assets, locations, drawings, maintenance, calibration, linked storage | Not audited |
| Operator & runtime | service/runtime operations | service lifecycle, jobs, storage enrollment, health and runtime state | Not audited |
| Reference data & connectors | platform/reference integrations | reference values, connector registration and platform parity | Not audited |
| Help & accessibility | accessibility and desktop help conventions | keyboard help, semantic controls, screen/route help, browser accessibility | Not audited |
| Backup/recovery & deployment-facing operations | backup/recovery and runtime utilities | web-visible controls only; deployment remains outside browser unless intentionally exposed | Not audited |

This table is only the starting inventory. It must be expanded from the actual Qt workflows before parity is claimed.

## Decision rule: keep, refactor or rebuild

**Keep** when behavior matches desktop, dependencies are explicit, wiring is certifiable and the implementation has a stable module boundary.

**Refactor** when behavior is substantially correct but the web code has hidden integration points, global state, cross-module DOM ownership, duplicated API knowledge or difficult-to-test wiring.

**Rebuild** when the current web implementation models the workflow incorrectly, has accumulated incompatible patches, or cannot expose a clear input/output contract without retaining coupling.

A rebuild decision applies to a web module, not automatically to the backend or whole application.

## Working rule

No parity fix is considered complete only because a button is visible or an endpoint exists. The module must prove the complete chain:

**capability → visible entry point → input validation → owned action wiring → API/application call → persisted/domain outcome → user-visible result → audit/test evidence**.
