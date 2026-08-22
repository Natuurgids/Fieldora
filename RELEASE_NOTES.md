# Fieldora 5.4.0 Research Map Context R29

- Research map toolbar is now map-specific; sampling, measurement and quality actions no longer leak into the map header.
- Project-stored map snapshots are preferred for the inline project preview.
- When no project snapshot is stored, the preview clearly directs users to the full Map workspace, which resolves installed OpenStreetMap/offline basemaps and applies project GIS layers as overlays.
- Double-clicking the project map preview opens the full map for the active project.

# Fieldora 5.4.1 Asset, Equipment & Facilities Operations R27

- Adds a clean-install Operations module for general equipment, maintainable assets, servicing, calibration and certification.
- Adds hierarchical physical storage from institution/site/building/floor/wing/hall/room through cabinet, drawer, shelf, box, tray and part codes.
- Supports exact storage paths such as Louvre / Hall 3 / 3rd floor / Left wing / Room 8 / Cabinet CS8-7 / Drawer 8 / Part C3.
- Adds storage-condition profiles for temperature, humidity, light, hazards and monitoring requirements.
- Adds asset images and governed documentation links including manuals, service reports, warranties and calibration certificates.
- Adds building drawing records for PDF, SVG, Visio, EdrawMax, IFC, DWG/DXF and raster plans, plus location-code markers with drawing coordinates.
- Adds maintenance and calibration event registers and asset location/movement schema.
- Adds equivalent clean-install PostgreSQL tables and shared Windows/Linux Qt screens. No migration is included.
- Adds server Operations APIs and a web workspace alongside the PostgreSQL persistence schema.

# Fieldora 5.4.1 Library Cold-Open R26

- Removes the duplicate V5 workspace refresh triggered by Home-tile/sidebar navigation.
- Defers the first unified Library catalogue load until the Qt event loop can display the workspace shell.
- Removes the full catalogue refresh from the Library constructor.
- Pages the unified catalogue in 200-asset batches with Previous/Next controls and a total active-asset count.
- Adds catalogue offset support so libraries larger than 2,000 assets remain reachable.
- Coalesces repeated Library refresh requests and disables table repainting while a page is populated.
- Adds a 4,000+ asset regression contract for cold-open paging and duplicate-refresh prevention.
- Retains all R25 runtime, R24 registry, Linux parity, and server parity fixes.

# Fieldora 5.4.1 Runtime Stabilization R25

- Adds the missing `ProjectManagementService.public_holidays()` and `add_public_holiday()` service operations used by project calendar restoration and holiday entry.
- Adds `ScienceWorkspace._refresh_dossier_project_choices()` and centralizes dossier project-combo refresh so workspace-context project changes cannot call an undefined callback.
- Adds runtime regressions for a clean project-management database, holiday persistence/range queries, and the Science workspace callback contract.
- Retains all R24 workspace-registry, constructor, installer, Linux parity, and server parity work.

# Fieldora 5.4.1 Workspace Registry R24

- Adds Platform Parity to the canonical V5 workspace registry in the same order used by `build_pages()`.
- Prevents startup failure when a page exists in the page factory but is absent from the registry contract.
- Adds regression coverage for registry/page-factory synchronization.
- Retains all constructor, Windows installer, Linux parity, and server parity work from R23.

# Fieldora 5.4.0 Constructor Stabilization R23

- Standardizes Research workspace context initialization before first refresh.
- Adds cross-package constructor-contract checks for context initialization and subscribed callbacks.
- Preserves existing clean-install data model and workflows.

# Fieldora 5.4.0 — Observations Workspace Construction R22

- Fixes the Observations workspace startup crash caused by subscribing to an undefined `_context_event` callback.
- Moves the observation context-refresh, change-notification, and review-action methods from the Library class to the Observations class where they belong.
- Adds safe workspace-context unsubscription when the Observations page closes.
- Adds a constructor regression test that verifies the subscribed callback exists on the Observations class and cannot leak into the Library class.
- Preserves all R21 installer import fixes and earlier server/Linux parity functions.

# Fieldora 5.4.0 — Installer Workspace Import R21

- Fixes missing `WorkspaceContext` import in the Qt Project Management module.
- Adds a package-wide regression test for all `WorkspaceContext` references.
- Preserves all R20 installer cleanup and server parity fixes.

# Fieldora 5.4.0 — Installer Workspace Context R20

This maintenance release fixes the Windows installer GUI smoke check failing with `NameError: WorkspaceContext is not defined`.

## Fixed
- Desktop application shell now explicitly imports the shared `WorkspaceContext` used after local login.
- Added regression coverage that verifies the login identity-change call has a matching import.
- Retains the R19 Windows SQLite cleanup fix and all R18 server parity functions.

## Scope
- No schema migration or user-data migration.
- Clean installation package.

# Fieldora 5.4.0 — Installer Verification R19

This maintenance release fixes the Windows installation verifier failure in the Fieldora Science GUI smoke check.

## Fixed
- Science workspace now unsubscribes from the process-wide workspace context when closed.
- Installer GUI verification marks the smoke-test widget for deletion and processes deferred Qt deletion events.
- Temporary verification-directory cleanup no longer fails installation when Windows briefly retains an SQLite file handle after successful GUI construction.
- Added regression coverage for Windows temporary SQLite cleanup and workspace-context release.

## Scope
- No scientific schema or user-data migration.
- Server parity functionality from R18 is retained.

# Fieldora 5.4.0 — Server Platform Parity R18

Build 18 completes the declared server functional surfaces for the cross-platform feature registry.

## Added
- Projects & Portfolio web workspace with phases, tasks, subtasks and sprints.
- Capacity & Availability web workspace with schedules, absences, obligations and allocations.
- Research operations APIs and web tabs for specimens, encounters, protocols, surveys, enrichments, samples and laboratory records.
- Observation bulk review controls.
- Dossier hierarchy, review and ownership web workspace.
- AI provider/model/MCP administration workspace.
- Reference-data and connector administration workspaces.
- Server parity release gate.

## Certification status
Functional parity is declared in the registry but remains uncertified until evidence-based Windows, Linux and server certification is completed.

# Fieldora 5.4.0 Portfolio & My Work — Build 16

- Added a cross-project Portfolio & My Work workspace limited to the current user's effective project access.
- Added consolidated hierarchy, Kanban, Grid, Gantt, Calendar, Workload, Resources, and Budget views.
- Platform administrators see all projects; managers and users see only authorized projects.
- Portfolio summaries use phase/task/subtask rollups, HR capacity, project allocations, realized hours, and budget variance.
- Double-clicking portfolio tasks opens the existing project task detail flow.


## 5.4.0 Phases, Sprints and Rollups R14

- Added persistent project phases and sprints.
- Tasks can be assigned to phases through the editor or by drag-and-drop in the hierarchy.
- Subtasks inherit and move with their parent phase.
- Added manual, calculated and effective estimates plus realized values.
- Phase estimates and realized values roll up from tasks; task values roll up from subtasks.
- Added planned and realized phase budgets with variance.
# Fieldora 5.4.0 Access Matrix — Build 13

- Added administrator-managed CRUD and functional access matrices.
- Added user, team, project, organisation, and all-data scopes.
- Added individual, aggregated, anonymized, statistical, and export representations.
- Added aggregated-only decisions that allow summaries while denying individual records.
- Platform administrators always receive unrestricted access across all projects and data scopes.
- Added effective-access simulation and complete audit attribution.

# Fieldora 5.4.0 Navigation & Startup — Build 8

This clean-install repair release centralizes the current-interface workspace registry and route contracts.

## Navigation and startup

- Every current-interface workspace is constructed through one explicit registry.
- Startup validates registry completeness, page uniqueness, route signals, and refresh contracts before the pages are connected.
- AI Review and Taxonomy aliases are normalized through the central route contract.
- Literal dashboard routes are checked against the actual workspace/context-route inventory.
- Unknown routes continue to fail visibly and may raise in strict test mode.

## Regression protection

- Replaces obsolete source-text route assertions with registry contract tests.
- Preserves existing project, media, administration, Research, and startup destinations.
- Clean-install release; no previous-release data migration is included.

# Fieldora 5.4.0 Dossier Review & Ownership — Build 6

This release completes the governed dossier workflow and corrects project visibility in Dossiers.

## Projects

- Independent dossier remains the first project option.
- The project selector now lists projects explicitly visible to the logged-in user.
- Legacy projects owned by the logged-in user remain selectable even when an older record lacks a membership row.

## Review workflow

- A dossier owner can defer a dossier to an enabled reviewer profile.
- While under review, dossier content is read-only to the reviewer and the original owner.
- The assigned reviewer can add timestamped remarks and return the dossier to the observer/owner.
- After return, the observer/owner can decide whether to change the dossier.
- A platform dossier administrator can reassign dossier ownership to another enabled user.
- Defer, review remarks, return and ownership reassignment are retained in the dossier review history with user and date/time.

## Permissions

- Dossier owners may edit their own dossiers except while review is active.
- Assigned reviewers may add review remarks but cannot alter dossier content.
- Platform administrators may reassign ownership and administer the workflow.

## Verification

- Dossier, project authorization, Research-context, Science persistence and portable-project tests passed.
- Python compilation and deployment preflight passed.

## Fieldora 5.4.0 Shared Context R7

- Adds a process-wide workspace context for the active identity and project.
- Centralizes accessible-project resolution, including explicit project ownership.
- Propagates identity, project, permission, and data refresh events across Project Management, Research Operations, and Dossiers.
- Removes the Project Management fallback to the synthetic `local-user` identity.
- Refreshes project membership permissions without restarting the application.
- Clean-install release; no previous-release data migration is included.

## 5.4.1 Operations Stabilization R28

- Enforces CRUD/access-matrix decisions for Operations assets, locations, drawings, documents, maintenance, calibration, movements and storage conditions.
- Adds administrator/home navigation entry points and module-toggle coverage for modern workspaces.
- Adds selection-aware Operations actions, record details, double-click open/edit flows, asset movement, document opening, drawing opening and maintenance/calibration completion.
- Removes direct SQLite access from the Qt Operations page; image and condition changes now use application-service methods and audit events.
- Wires the PostgreSQL Operations schema into server repository initialization and mirrors Operations writes into typed PostgreSQL tables.
- Adds server routes for asset documents, storage conditions, drawing markers and movements.
