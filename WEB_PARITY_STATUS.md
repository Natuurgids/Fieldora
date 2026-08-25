# Fieldora web parity live status

Last updated: 2026-08-25

Read this file together with:

- `WEB_DESKTOP_PARITY_PLAN.md` — full 60-item work breakdown and acceptance contracts.
- `WEB_PARITY_IMPORT_CONTRACT.md` — detailed import/evidence identity source trace and target architecture.
- `WEB_PARITY_PROJECT_CONTRACT.md` — authoritative desktop/server/web Project creation trace and target contract.

This file is deliberately short. It is the current-session handoff/status board and should be updated whenever a slice changes state.

## Current branch state

Branch: `feature/versioned-facility-floorplans`

The Windows 11 + Docker Desktop clean installation has been runtime-validated by the user and the Rocky Linux 9 application image was built successfully. Runtime use then exposed desktop/web functional divergence; this program addresses that divergence.

## In progress

| Work | State | Current evidence / next action |
|---|---|---|
| WEB-006 authoritative duplicate-flow trace | DONE (analysis) | Source trace is recorded in `WEB_PARITY_IMPORT_CONTRACT.md`. Desktop uses production `ImportService.plan()/execute()`; browser currently implements a separate upload loop. |
| WEB-007 canonical evidence identity | PARTIAL | Same organization + same project + same verified SHA-256/size now converges to one media identity in filesystem/SQLite and PostgreSQL metadata paths. Organization-wide identity across project contexts remains WEB-011 because project visibility must move to associations first. |
| WEB-008 exact duplicate no-op | DONE (same context) | Repeated verified upload/register in the same organization/project returns the canonical existing media record, creates no second media row, and removes redundant temporary/object bytes. `Fieldora media identity certification` run #4 is green on reference/SQLite and PostgreSQL. |
| WEB-012 dedup race safety | PARTIAL | PostgreSQL completion uses transaction-scoped advisory serialization around content identity and is certified. SQLite/reference concurrency still needs an explicit race test/transaction strategy. |
| WEB-015 reproduce multi-file browser fetch failure | ANALYSIS | Confirmed browser uses 4 MiB chunks; regular and staged APIs allow up to 8 MiB and the HTTP adapter has no smaller obvious body cap. Need a real managed-server Playwright request trace before changing behavior. |
| WEB-011 project link on existing evidence | READY | `media_links.py` already models organization-owned media plus project/collection/etc. associations. It is not yet wired into the main media upload/list path; do not broaden hash identity across projects until visibility/link semantics are wired. |
| WEB-026 unusable Create Project button | PARTIAL | The structural cause is fixed for managed PostgreSQL: browser creation now enters authoritative PM persistence rather than Science-only snapshots. A real managed-browser click/runtime check is still required before this item is DONE. |
| WEB-027 desktop Project creation trace | DONE (analysis) | `WEB_PARITY_PROJECT_CONTRACT.md` records that authoritative creation validates dates, creates the canonical ID, five workflow statuses, admin PM membership, activity and optional template state. |
| WEB-028 shared web Project creation contract | DONE (managed creation subset) | Managed PostgreSQL creation is organization-scoped, server-ID authoritative, creates desktop-equivalent default statuses/admin PM membership/activity, and remains PBAC-gated. `Fieldora project parity certification` run #1 is green. Templates and later edit/archive/child work remain separate WEB-029–032 slices. |

## Evidence-identity slice commits

- `2831150daf9b708a1d84ecb01be177bbb12a82dc` — PostgreSQL same-context canonical content completion.
- `d810b803e74a0511798ed9f67a21e066f4875b3f` — governed media store returns canonical record and removes redundant bytes.
- `70a94bc50ea18b5ebed8f9ebac62cebced31ee14` — filesystem/reference identity tests.
- `9193475a819d2dfd22d968e98e4815a375232d03` — PostgreSQL identity test.
- `9512eb699728109df188402a66d5792f06bd3694` — dedicated media identity certification workflow.
- `9789297c9645f2103d8d14fd95c7a299d020cce0` — repair PostgreSQL advisory key after run #1 exposed illegal NUL separators.

## Project creation slice commits

- `7758cfa3015331c30d89cc29a06ee43b178a0212` — Project creation parity contract/source trace.
- `70b2837066d065e1e84597d55667437e7c61faf5` — initial managed PostgreSQL PM creation adapter.
- `21eb14d78ef95a45e46b6dc0bb8b0d2b17ab54d7` — managed browser API Project Management hook.
- `eeacf3a8` — organization-scope managed PM persistence.
- `d4ba18f9` — organization-scope managed browser Project API.
- `4666f594` — compose PostgreSQL PM service into managed `serve` runtime.
- `39a1a737` — managed browser API canonical-ID/PBAC tests.
- `dff0f36cbf99de17703b4f6bb38e11bc789cf6f3` — dedicated Project parity certification workflow.

## Certification history

### Fieldora media identity certification — run #1

Result: FAILED usefully.

- Ruff passed.
- 3 filesystem/reference tests passed.
- PostgreSQL test failed before exercising identity logic because the advisory lock key contained NUL separators, which PostgreSQL text parameters reject.
- Commit `9789297c9645f2103d8d14fd95c7a299d020cce0` replaced that key with SHA-256 hex text.

### Fieldora media identity certification — run #4

Result: SUCCESS.

- PostgreSQL 16 service initialized successfully.
- Ruff governed-media identity check passed.
- Filesystem/reference identity tests passed.
- PostgreSQL governed-media identity test passed.
- This certifies same-context exact duplicate no-op and the PostgreSQL transaction-serialized canonical completion path.

### Fieldora project parity certification — run #1

Result: SUCCESS (run `32882236322`, job `97914262275`).

- PostgreSQL 16 service initialized successfully.
- Ruff managed Project parity check passed.
- PostgreSQL Project creation contract tests passed: canonical project, exact desktop default statuses, admin PM membership, `project.created` activity, date validation and organization isolation.
- Managed API tests passed: browser-provided IDs do not become authoritative, authenticated organization is used, and PBAC denial persists nothing.
- Broader server-web, zero-trust and Platform regression lanes from the same branch head must also remain green before runtime handoff.

## Guardrails

1. Do not modify the job-engine lease implementation to solve web parity defects.
2. Do not duplicate domain/application business rules in browser JavaScript.
3. Do not equate a repeated byte transfer with a new scientific observation.
4. Do not represent a new project relationship by copying evidence bytes or inventing a second evidence identity.
5. Preserve PBAC/zero-trust authorization at every new API/application adapter.
6. Every completed slice needs focused tests and a named certification result.

## Resume instructions for a new session

1. Read this file.
2. Read `WEB_DESKTOP_PARITY_PLAN.md`.
3. For import work, read `WEB_PARITY_IMPORT_CONTRACT.md`.
4. For Project work, read `WEB_PARITY_PROJECT_CONTRACT.md`.
5. Inspect the current branch head and latest workflow runs before editing.
6. Finish any `BUILDING`/`PARTIAL` item before starting unrelated parity work unless a failed test shows the design is wrong.
7. Update this status file when the slice changes state.
