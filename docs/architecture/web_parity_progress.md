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

**Iteration 6 evidence:** `src/natureai_next/server/project_core_module_web.py` owns a dedicated Projects work hierarchy and loads Project evidence through the association-aware governed `/api/v1/media?project_id=...` endpoint, so both directly assigned and explicitly linked evidence appear in the Projects-owned evidence surface. `src/natureai_next/server/project_creation_module_web.py` owns top-level Project creation, validates required name, budget and date ordering, posts only user-entered Project fields to `/api/v1/projects`, reloads Projects/Core after persistence, and leaves active status plus creator ownership to the server. `src/natureai_next/server/project_work_actions_module_web.py` owns creation of phases, tasks, milestones, subtasks, sprints and allocations with visible validation, capability-aware discoverability and post-persistence refresh. `src/natureai_next/server/project_lifecycle_module_web.py` owns selected-project edit, status and archive controls while preserving expected-revision conflict handling and capability projection. `src/natureai_next/server/project_evidence_actions_module_web.py` owns linking existing governed Library evidence to the selected Project, uses Project edit capability only for discoverability, calls the server-owned `/media-links` contract, preserves evidence identity/provenance, and refreshes the Projects/Core evidence surface through `fieldora:project-evidence-changed`. `src/natureai_next/server/project_progress_module_web.py` now owns three desktop-familiar planning views: the Project progress overview, a workflow-status Kanban board, and a date-driven Gantt timeline. Kanban supports capability-aware drag/drop and keyboard-accessible status selects; every status move PATCHes the governed task endpoint, whose server-side Project and task edit decisions remain authoritative. The Gantt view follows the desktop date fallback (`start_date or due_date`, `due_date or start_date`), normalizes reversed ranges, shows progress/blocking/done cues, and opens the module-owned task editor. `src/natureai_next/application/project_task_detail.py` provides a lossless task-detail read model for fields omitted from planning summaries. `src/natureai_next/server/project_task_edit_module_web.py` owns desktop-familiar task editing for title, description, owner, workflow status, priority, dates, estimate/realized effort, progress, budget, phase, sprint, recurrence and milestone state; its detail GET requires Project and task view decisions, while PATCH independently requires Project and task edit decisions. `src/natureai_next/server/project_task_editing.py` now provides a storage-neutral task detail/update facade and a desktop-density managed task-list projection. Managed hierarchy reads expose authoritative workflow status id/name/category, progress, blocked status, owner/assignee aliases, estimate/realized effort aliases, budget, recurrence, phase and sprint context instead of forcing Kanban/Gantt/progress to infer those fields from reduced summaries. The same browser contract therefore works against both the local SQLite service and managed PostgreSQL Project service rather than assuming a local `database_path`. `web_module_contracts.py` assigns task editing, planning-view selection, Kanban status movement, Gantt inspection and the other Project actions to `projects.core`. Cross-domain Project integrations stay outside Projects/Core: `capacity` owns project allocation/capacity navigation and `research.dossiers` owns project research-record navigation. `src/natureai_next/server/project_research_integration_web.py` now consumes the public Projects context event/API, mounts a Research-owned `Open research` entry point only while Projects is active, navigates through `FieldoraModules`, and hands the selected Project to the public `FieldoraResearchRecords.openProject` contract without touching Research form DOM or replacing Research globals. `src/natureai_next/server/project_capacity_integration_web.py` applies the same boundary for Capacity: the visible `Open capacity` entry point is Capacity-owned, consumes public Projects context, navigates through the shell and hands the Project to `FieldoraCapacity.openProject` rather than making Projects/Core render Capacity state. `modular_shell_web.py` removes the old generic Project-creation fragment, WEB-032 hierarchy owner, WEB-031 lifecycle patch, and only after both work/evidence replacement owners exist, the combined WEB-058 Project runtime browser patch; all governed server APIs remain in place. Tests cover action ownership, lossless task-detail reads, local-summary preservation, managed planning-field projection, task-editor wiring and validation, association-aware evidence loading, progress/Kanban/Gantt wiring, bounded Research and Capacity integration ownership, absence of Portfolio/global-renderer coupling and ownership-gated removal of competing browser fragments. Dependency-derived blocking remains richer in the local desktop service than the managed PostgreSQL adapter, and browser/final-DOM certification remains outstanding, so no Projects requirement is marked complete yet.

### Iteration 7 — Portfolio and project integrations
- [~] Portfolio views
- [~] Cross-project overview without merging ownership into Projects/Core
- [~] Capacity/availability links
- [~] Research/dossier links
- [ ] Portable project package exchange
- [ ] Project reporting/export integration through public contracts

**Iteration 7 evidence:** `src/natureai_next/server/portfolio_module_web.py` owns Portfolio view selection, scope selection, lifecycle mount/unmount, project-open interaction and user-visible module errors without replacing `loadPortfolio`, `showPage`, or another feature global. `web_module_contracts.py` assigns `portfolio.view.select`, `portfolio.scope.select`, and `portfolio.project.open` to `portfolio`; `portfolio` remains dependent on but separate from `projects.core`. The same registry establishes bounded `capacity` and `research.dossiers` integration contracts: Capacity owns Project navigation, allocation viewing and its availability actions; Research owns `research.project.open` and `research.project.records.view`; neither domain is owned by Projects/Core. `project_research_integration_web.py` provides the visible Projects → Research entry point and consumes only public module contracts. `research_records_web.py` exposes `FieldoraResearchRecords.openProject`, which preserves the selected Project as Research-owned context and reloads the current domain through the governed project-filtered Research API. The Research API performs PBAC per record and project context. `project_capacity_integration_web.py` now provides the equivalent visible lifecycle-owned Projects → Capacity entry point, and `capacity_module_web.py` publishes Capacity Project-context changes for independently mounted Capacity slices. `capacity_availability_module_web.py` consumes that public event rather than reaching into Projects DOM or globals. Capacity/availability remains `[~]` because the managed PostgreSQL Project backend still needs equivalent schedule/absence/obligation persistence support and browser/final-DOM certification is outstanding. `modular_shell_web.py` removes both the former Portfolio override from shared navigation compatibility and the duplicate Portfolio renderer/global `loadPortfolio` wrapper embedded in `project_facility_workspace_web.py` from the final served client. The existing Portfolio loader remains a transitional data integration adapter.

### Iteration 8 — Capacity, research and dossiers
- [~] Schedules/absences/allocations
- [~] Research records/dossiers
- [ ] Dossier-media stable-ID boundary
- [~] Cross-module project integration tests

**Iteration 8 evidence:** The Qt Project workspace defines one Availability view with `User`, `Scheduled`, `Absence`, `Organisation`, `Allocated`, `Remaining` and `Status` columns plus `Assign schedule`, `Register absence`, `Add organisational obligation` and `Allocate to project` actions. Its user-facing contract explicitly says Project users see availability impact while HR/private details remain governed. `src/natureai_next/server/capacity_module_web.py` retains the Project-scoped allocation surface backed by the governed allocation API. `src/natureai_next/server/capacity_availability_module_web.py` now owns the remaining aggregate availability slice: GET `/api/v1/capacity/availability` returns the shared Project Management `workload()` projection and active schedule templates after Project-view authorization, while schedule, absence and organisational-obligation writes require Project-edit authorization and a target user who is actually a Project member. The browser adapter exposes the desktop-recognizable actions and aggregate availability impact but does not send private absence notes or privacy metadata to the client. Local SQLite persistence delegates to the authoritative `schedule_templates`, `assign_work_schedule`, `add_absence` and `add_organisational_obligation` service methods. If the configured Project backend lacks those authoritative operations, the API returns `capacity_backend_unavailable` instead of silently falling back to the legacy generic web records. Managed PostgreSQL capacity persistence, audit/provenance confirmation and browser/final-DOM certification remain outstanding, so this requirement stays `[~]`.

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
