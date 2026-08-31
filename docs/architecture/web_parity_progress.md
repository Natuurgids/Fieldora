# Desktop/Web Modular Parity — Build Progress

This file is the branch-visible implementation checklist for the desktop-to-web parity rebuild.

**Active branch:** `audit/desktop-web-modular-parity`  
**Draft PR:** #3 — keep draft and unmerged until parity certification is complete.  
**Behavioral reference:** Qt desktop. The existing web client is evidence, not the specification.

## Status model

- [ ] Not started
- [~] In progress
- [x] Implemented, tested, and parity verified
- [!] Blocked / decision required

A requirement may be marked `[x]` only when this complete chain is demonstrated:

`desktop capability -> visible web entry point -> input validation -> module-owned action wiring -> application/API call -> server authorization -> persisted/domain result -> user-visible result -> automated test -> parity verification`

UI presence alone never counts as completion. Hidden or disabled controls never substitute for server-side authorization.

## Module contract gate

Every module must document and test:

- [ ] Inputs and validation
- [ ] Outputs and user-visible feedback
- [ ] Owned routes / visible entry points
- [ ] Integration points and public contracts
- [ ] Runtime/environment dependencies
- [ ] Authentication and authorization requirements
- [ ] Lifecycle / mount / unmount behavior
- [ ] Failure, retry and cancellation behavior where applicable
- [ ] Persistence/domain effects
- [ ] Audit/provenance behavior where applicable
- [ ] Automated contract/integration tests
- [ ] Browser/final-DOM wiring verification

## Iteration plan

### Iteration 1 — Platform and shell foundation
- [x] Establish branch-visible parity checklist and definition of done
- [~] Explicit web workspace/module registry
- [~] Route ownership and normalization contract
- [~] Module mount/unmount lifecycle
- [~] Remove dependence on cross-feature global DOM manipulation for migrated modules
- [ ] Platform notification/error boundary
- [~] Module contract test harness

**Iteration 1 evidence:** `src/natureai_next/server/web_module_contracts.py` defines framework-independent module metadata, route/action ownership and dependency validation, with separate ownership for `projects.core` and `portfolio`. `src/natureai_next/server/web_module_runtime.py` provides explicit mount/unmount lifecycle state and failure isolation. `src/natureai_next/server/modular_shell_web.py` bridges that registry into the served browser shell and removes migrated compatibility responsibilities. A production-order audit found that HTTP compatibility patches are appended after the API mixin response, so `src/natureai_next/server/http.py` now runs `patch_modular_shell_response` as the final managed-browser finalizer. The finalizer relocates the unique shell bootstrap to the end of `/app.js`, ensuring legacy DOM construction and feature adapters exist before initial module-mount events fire. `tests/test_modular_shell_web.py` now covers this real production patch order rather than only synthetic patch order. CI/browser certification is still required before these items can be marked complete.

### Iteration 2 — Identity, session and capabilities
- [ ] Local credential sign-in parity
- [ ] OIDC/network authentication adapter where configured
- [ ] Session termination/logout
- [ ] Capability/PBAC projection to the web client
- [ ] Independent API/server authorization verification
- [ ] Unauthorized/expired-session user-visible behavior

### Iteration 3 — Library and evidence foundation
- [ ] Library catalog browsing and paging/virtualization
- [ ] Quick search
- [ ] Structured filters
- [ ] Import files/folders
- [ ] Managed/linked/hybrid storage-policy behavior
- [ ] Trash/restore/permanent-delete workflow

### Iteration 4 — Viewer, collections and evidence workflows
- [ ] Full media viewer
- [ ] Saved searches
- [ ] Collections
- [ ] Viewer/library context preservation
- [ ] Evidence integration contracts for observations/projects/research

### Iteration 5 — Observations
- [ ] Observation list/detail
- [ ] Create/edit observation
- [ ] Accept/reject/defer/reverse review workflow
- [ ] Observation history/evidence timeline
- [ ] Life lists/statistics

### Iteration 6 — Projects core — desktop-familiar workflow
Projects are a high-fidelity parity area. The web workflow, hierarchy and terminology should remain recognizable to desktop users while implementation boundaries stay modular.

- [~] Project list and project context
- [~] Project create/edit lifecycle
- [~] Desktop-similar work hierarchy
- [~] Phases/tasks/work-item navigation and editing
- [~] Project status/progress behavior
- [~] Project-to-evidence/observation/research links
- [~] Project module owns its actions; no unrelated DOM coupling
- [~] Project API authorization and persistence verified
- [~] Project workflow parity tests

**Iteration 6 evidence:** `src/natureai_next/server/project_core_module_web.py` owns a dedicated Projects work hierarchy surface backed directly by the governed `/api/v1/phases`, `/api/v1/tasks`, `/api/v1/sprints`, and `/api/v1/allocations` endpoints rather than Portfolio DOM datasets. `src/natureai_next/server/project_work_actions_module_web.py` owns creation of phases, tasks, milestones, subtasks, sprints and allocations with visible validation, capability-aware discoverability and post-persistence refresh through `fieldora:project-work-changed`. `src/natureai_next/server/project_lifecycle_module_web.py` now owns selected-project edit, status and archive controls. It preserves expected-revision mutation, revision-conflict reload/review behavior, project-name/budget/date validation, capability projection and user-visible errors while refreshing Projects/Core directly instead of calling Portfolio. `web_module_contracts.py` assigns the work-creation actions plus `projects.details.edit`, `projects.status.change`, and `projects.archive` to `projects.core`. `modular_shell_web.py` retires both the former WEB-032 hierarchy browser owner and the older Project lifecycle browser patch when their replacement owners are present; the managed hierarchy/lifecycle server APIs remain independently authoritative for authentication, PBAC, validation, audit and persistence. Tests cover module ownership, absence of Portfolio/global-renderer coupling, revision-conflict behavior and ownership-gated removal of the old lifecycle patch. Top-level Project creation is still on the existing client path, detailed status/progress parity and browser/final-DOM certification remain outstanding, so no Projects requirement is marked complete yet.

### Iteration 7 — Portfolio and project integrations
- [~] Portfolio views
- [~] Cross-project overview without merging ownership into Projects/Core
- [ ] Capacity/availability links
- [ ] Research/dossier links
- [ ] Portable project package exchange
- [ ] Project reporting/export integration through public contracts

**Iteration 7 evidence:** `src/natureai_next/server/portfolio_module_web.py` owns Portfolio view selection, scope selection, lifecycle mount/unmount, project-open interaction and user-visible module errors without replacing `loadPortfolio`, `showPage`, or another feature global. `web_module_contracts.py` assigns `portfolio.view.select`, `portfolio.scope.select`, and `portfolio.project.open` to `portfolio`; `portfolio` remains dependent on but separate from `projects.core`. `modular_shell_web.py` removes both the former Portfolio override from shared navigation compatibility and the duplicate Portfolio renderer/global `loadPortfolio` wrapper embedded in `project_facility_workspace_web.py` from the final served client. The existing loader remains a transitional data integration adapter. CI and browser/final-DOM certification are still required, so these items remain in progress rather than complete.

### Iteration 8 — Capacity, research and dossiers
- [ ] Schedules/absences/allocations
- [ ] Research records/dossiers
- [ ] Dossier-media stable-ID boundary
- [ ] Cross-module project integration tests

### Iteration 9 — AI Review and Knowledge
- [ ] AI review queue
- [ ] Accept/reject/defer/reverse
- [ ] Single-photo accept/reject-rest workflow
- [ ] Generate AI analysis as background work
- [ ] Knowledge Center
- [ ] Name preferences
- [ ] Conservation/seasonality context

### Iteration 10 — Administration and governance
Administration remains a coordinator/shell with focused subroutes, not one giant page.

- [ ] Administration coordinator shell
- [ ] User management
- [ ] Roles/groups/contracts/policies
- [ ] Access administration
- [ ] Decision/audit inspection
- [ ] AI resource setup
- [ ] Connector/integration management

### Iteration 11 — Operator, facilities and reference modules
- [ ] Jobs center
- [ ] Runtime/service health
- [ ] Optional subsystem isolation
- [ ] Facilities/locations/assets
- [ ] Floorplans/drawings after desktop parity confirmation
- [ ] Maintenance/calibration after desktop parity confirmation
- [ ] Taxonomy/reference packages
- [ ] Offline map workspace where supported

### Iteration 12 — Export, reporting, backup and recovery
- [ ] Export assets
- [ ] Export data
- [ ] Generate reports
- [ ] Permission-aware export/report scope
- [ ] Verified backup
- [ ] Restore/recovery
- [ ] Deployment-facing operations boundary

### Iteration 13 — Accessibility, localization and UX certification
- [ ] Keyboard-first operation
- [ ] Accessible semantics
- [ ] Error/notification consistency
- [ ] Localization boundaries
- [ ] Normal desktop viewport fit
- [ ] Persisted shell/view preferences where appropriate

### Iteration 14 — Final parity certification
- [ ] Full requirement-to-module trace
- [ ] Final-DOM/control wiring audit
- [ ] API authorization audit
- [ ] Persistence/result verification
- [ ] Cross-browser certification
- [ ] Regression suite
- [ ] Remove superseded compatibility-patch/global-DOM mechanisms
- [ ] No unexplained desktop/web parity gaps remain

## Modular target map

| Domain | Web ownership |
| --- | --- |
| Shell/navigation | `platform/module-runtime`, `shell/router`, `shell/commands` |
| Identity/access | `identity/session`, `identity/provider-adapter`, `authorization/capabilities` |
| Home | `home/activity` |
| Library | `library/catalog`, `library/search`, `library/import`, `library/trash` |
| Viewer | `viewer` |
| Collections | `collections` |
| Observations | `observations`, `observation-history`, `statistics` |
| Projects | `projects/core` |
| Portfolio | `portfolio` |
| Capacity | `capacity` |
| Research | `research/dossiers` |
| AI review | `ai-review`, `ai-jobs` |
| Knowledge | `knowledge-center` |
| AI setup | `ai-resources` |
| Administration | `admin-shell` plus focused `users`, `access-policy`, `audit`, `operations`, `integrations`, `storage-archives` modules |
| Facilities | `facilities` |
| Operations | `operator/jobs` |
| Reference/connectors | `reference-data`, `connectors` |
| Maps | `maps` when desktop scope is confirmed |
| Export/reporting | `export`, `reporting` |
| Shared platform | notifications, accessibility, i18n, audit/provenance, testing |

## Progress discipline

1. Update this checklist in the same branch as implementation work.
2. Keep the detailed requirements spreadsheet synchronized with module/status/evidence/test fields.
3. Do not mark a feature done because markup or a button exists.
4. Record tests and implementation evidence before checking a requirement off.
5. Refactor or rebuild web code when existing coupling prevents a clean module contract; preserve working domain, persistence, security, audit, API and deployment foundations.
6. Keep Projects visually and behaviorally close to the desktop workflow, but keep Projects/Core, Portfolio, Capacity, Research and Export/Reporting separated by explicit contracts.
