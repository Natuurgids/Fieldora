# WEB-027 — desktop Project creation contract trace

This trace records the authoritative desktop Project creation path before web parity work is certified.

## Desktop presentation path

`src/natureai_next/ui/qt/project_management.py` owns only presentation concerns for the New project action. The dialog collects a required project name, an owner identity (defaulting to the current actor), and an optional due date. On acceptance it calls `ProjectManagementService.create_project(...)`, stores the returned project ID in the workspace selection, and refreshes the Project view. It does not construct or persist a separate Qt-only Project record.

## Shared application contract

`src/natureai_next/application/project_management.py` defines `ProjectManagementService` as the transactional work-management service shared by desktop and server UI. Project creation:

- rejects a blank name;
- validates ISO project dates and rejects a due date before the start date;
- creates the Project identity in the application service;
- trims name/description/owner and defaults status to `active`, budget to `0`, and currency to `EUR`;
- initializes the standard workflow statuses;
- grants the selected owner the Project `admin` membership in the desktop application store;
- records the `project.created` activity event with the creating actor;
- returns the created Project ID so the caller can select/reopen the authoritative record.

Creation has no incoming optimistic revision because the identity does not yet exist. The initial persisted `updated_at_us` is the creation revision/timestamp. Managed web creation returns the revision of the authoritative created row; subsequent edit/status/archive mutations require an explicit expected revision.

## Managed web mapping

The managed browser API must remain a transport/authorization adapter. `POST /api/v1/projects` authenticates the caller, evaluates PBAC `create project`, and delegates to the managed Project Management service. Organization, owner, and actor authority come from the authenticated identity, not browser-selected IDs. The service-generated Project identity, default active status, persisted fields, audit semantics, and returned revision are authoritative.

The browser may collect the same user-editable fields, but it must not invent ownership, status, revision, Project identity, or persistence semantics in JavaScript.

## Certification

Focused certification is `tests/test_web027_project_creation_trace.py` plus the WEB-027 workflow. It proves the Qt action delegates to the shared service and that desktop creation persists the documented defaults, owner membership, audit event, initial revision timestamp, and returned selection identity.
