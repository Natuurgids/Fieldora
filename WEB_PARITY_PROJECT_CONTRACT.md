# Fieldora web parity — project creation contract

Status: implementation contract for `WEB-026` through `WEB-032` in `WEB_DESKTOP_PARITY_PLAN.md`.

This document records the desktop/server/web source trace for Project creation so future implementation sessions can resume without relying on chat history.

## 1. Authoritative desktop project model

`src/natureai_next/application/project_management.py` defines `ProjectManagementService` as the transactional work-management service shared by desktop and server UI.

The authoritative `create_project()` contract does substantially more than create a display record:

1. requires a non-empty project name;
2. validates optional start and due dates as ISO `YYYY-MM-DD`;
3. rejects a due date before the start date;
4. allocates the canonical project ID in the service;
5. inserts the full `pm_projects` row with description, owner, dates, budget, currency and optional template;
6. creates the default workflow statuses:
   - To Do
   - In Progress
   - QA
   - Blocked
   - Done
7. adds the owner (or actor fallback) to `pm_project_members` as `admin`;
8. records a `project.created` activity event;
9. applies the selected project template, when supplied.

This state is subsequently used by tasks, phases, sprints, workload/capacity, research areas, specimens, surveys, measurements, samples, project media, project notes, quality checks, exports and project authorization.

Therefore a lightweight project record stored elsewhere is not functionally equivalent to a Project Management project.

## 2. Current browser divergence

`src/natureai_next/server/browser_functionality_web.py` currently adds its own Project editor in browser JavaScript. The browser:

- generates `id` with `crypto.randomUUID()`;
- collects only name, status and description;
- copies the current identity into `owner_id`;
- POSTs the browser-built record to `/api/v1/projects`.

`src/natureai_next/server/browser_functionality_api.py` intercepts that POST in `BrowserFunctionalityFieldoraApi._create_project()`.

That browser-specific API path:

1. authenticates the identity;
2. validates only the supplied record ID and name;
3. performs a PBAC `create/project` decision;
4. persists the supplied object through `_science.put("projects", record, ...)`;
5. creates a project-scoped PBAC object grant for the creator.

It does **not** call `ProjectManagementService.create_project()`.

Consequently the browser-created project can exist in the Science snapshot while lacking the authoritative Project Management state: workflow statuses, PM membership, PM activity, validated dates/budget/currency/template behavior and the data relationships expected by the mature desktop workspace.

This is a structural parity defect, not merely a broken button.

## 3. Target contract

The web/API route must become a transport and authorization adapter around the same Project Management creation command used by desktop.

Desired sequence:

1. authenticate browser identity;
2. authorize `create/project` through the existing PBAC decision layer;
3. parse a transport DTO containing the fields supported by the shared command;
4. call the authoritative Project Management application service to create the project;
5. establish any additional server PBAC projection/grant needed for distributed access without replacing PM membership semantics;
6. return the canonical project ID and normalized project summary;
7. refresh the Projects/Portfolio view from the authoritative project source.

The browser must not generate the authoritative project identity itself.

## 4. Fields and validation

The first parity version should support at least:

- `name` — required;
- `description`;
- `owner_id` — default to authenticated creator unless an authorized administrative workflow chooses another owner;
- `start_date` — optional ISO date;
- `due_date` — optional ISO date, cannot precede start;
- `budget` — numeric, default 0;
- `currency` — default EUR;
- `template_id` — optional.

Project lifecycle/status should follow the Project Management service rather than accepting arbitrary browser-provided initial state. The service currently creates projects as `active`.

## 5. Authorization layering

PBAC remains authoritative at the server boundary.

Project Management membership/role is not a replacement for platform PBAC. Both layers have distinct purposes:

- PBAC determines whether the authenticated server caller may invoke/create/disclose the resource;
- Project Management membership/role governs work-management permissions inside the created project;
- project state supplies additional ABAC behavior (for example archived/cancelled edits);
- later contracts/explicit denies remain authoritative where applicable.

The creator must emerge with the intended immediate access in both layers, but no global administrator bypass may be introduced.

## 6. Persistence/server architecture question

The current `ProjectManagementService` is SQLite-backed. The managed Fieldora server deployment is PostgreSQL-oriented and multi-node capable.

Do **not** simply point the distributed server at a process-local SQLite PM database to achieve UI parity.

Before changing `/api/v1/projects`, inspect the existing server project/portfolio adapters and persistence composition. The correct implementation is one of:

1. an existing PostgreSQL-capable Project Management repository/service already present in the branch, wired into the browser/API; or
2. a presentation-neutral Project Management command/repository abstraction with SQLite and PostgreSQL adapters that preserve the same business contract.

The desktop service is the behavioral reference, not necessarily the final server storage adapter.

## 7. Required tests

### WEB-026 — reproduce current browser failure

A managed-web Playwright test must:

1. authenticate with an identity allowed to create projects;
2. navigate to Projects & Portfolio;
3. click the actual `Add project` / Create control;
4. fill a valid project name;
5. submit;
6. capture the current failure or incomplete persistence before the implementation changes.

The test should inspect the network/API result and authoritative project storage state, not only whether a dialog disappears.

### WEB-027 — shared service contract

Application-level tests must prove creation establishes:

- one canonical project;
- all five default statuses;
- owner/admin PM membership;
- `project.created` activity;
- date validation;
- optional template application.

### WEB-028 — web adapter parity

API/browser tests must prove the same postconditions after web creation, plus:

- PBAC denial creates nothing;
- the creator can immediately open the project;
- the returned ID is the service-generated canonical ID;
- no orphan/lightweight duplicate project snapshot is created in a parallel store.

PostgreSQL parity is required for the managed-server persistence adapter.

## 8. Follow-on lifecycle slices

After creation parity is green, handle separately:

- WEB-029 validation parity;
- WEB-030 immediate creator authority;
- WEB-031 edit/archive/revision lifecycle;
- WEB-032 phase/task/sprint/allocation child creation and real portfolio views.

Do not broaden WEB-028 into all Project Management functionality in one change.

## 9. Do not do

- Do not repair the button by only changing JavaScript.
- Do not keep a browser-only Project data model alongside the authoritative PM model.
- Do not let the browser choose canonical IDs.
- Do not bypass PBAC because PM membership says `admin`.
- Do not introduce process-local SQLite into the distributed PostgreSQL server merely to reuse the desktop implementation literally.
- Do not mark Project creation complete because a card appears; verify the workflow statuses, membership and activity postconditions.
