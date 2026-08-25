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
| WEB-007 canonical evidence identity | DONE (organization canonical) | Same organization + same verified SHA-256/size converges to one media identity across project contexts in reference/SQLite and PostgreSQL paths. `Fieldora media identity and project association certification` run #26 is green. |
| WEB-008 exact duplicate no-op | DONE (same context) | Repeated verified upload/register in the same organization/project returns the canonical existing media record, creates no second media row, and removes redundant temporary/object bytes. `Fieldora media identity certification` run #4 is green on reference/SQLite and PostgreSQL. |
| WEB-012 dedup race safety | PARTIAL | PostgreSQL completion uses transaction-scoped advisory serialization around content identity and is certified. SQLite/reference concurrency still needs an explicit race test/transaction strategy. |
| WEB-015 reproduce multi-file browser fetch failure | ANALYSIS | Confirmed browser uses 4 MiB chunks; regular and staged APIs allow up to 8 MiB and the HTTP adapter has no smaller obvious body cap. Need a real managed-server Playwright request trace before changing behavior. |
| WEB-011 project link on existing evidence | DONE | Upload completion records project associations against the organization-canonical media identity. Project A/B both list and download the same canonical object, an unlinked Project C receives no listing and a 404 download, and PostgreSQL persists two distinct project association rows. Run #26 is green. |
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

## WEB-011 project-association slice commits

- `78d5f56f2f402321ed39c64c68a0a91f561e1e83` — canonicalize governed media across Project contexts.
- `6fb6713b6853927025c7c4f92f18c60748eef258` — query governed media associations by target Project.
- `614516411100f02558f812e71f77986ec8287189` — canonicalize PostgreSQL media across Project contexts.
- `0889371a1090e08f3d25bea42624110463abbbc3` — expose PostgreSQL media associations beside canonical metadata.
- `197fb951de4ac4870ed41f48bf282fc5adda199a` — attach governed associations to the media store.
- `475701d3c1349745634e492de46c2c94c938f54e` — wire Project associations into browser media upload/list/download access.
- `3b7178520be5e67f7b589c6a21d7cd4e3c0b5351` — certify browser canonical-media Project association behavior.
- `bea1390a8c642b512a1859ff212ec98cfbd690ae` — certify PostgreSQL canonical-media Project association persistence.
- `4548021f164bc5438c662f1537a2580420c094d4` — extend the named media certification workflow to WEB-011.
- `715b0dc6daa14a3081a4a0ede37002f603dada3e` — initialize the managed Project fixture required by the broader browser test file.

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

### Fieldora media identity and project association certification — run #25

Result: FAILED usefully (run `32899240337`, job `97968911395`).

- PostgreSQL 16 service initialized successfully.
- Ruff passed.
- The new WEB-011 canonical-media, Project-association, scoped list/download and PostgreSQL assertions passed.
- Three pre-existing Project creation tests failed because their `__new__` fixture did not initialize the newly introduced `_project_management` constructor state.
- Commit `715b0dc6daa14a3081a4a0ede37002f603dada3e` fixes the fixture without weakening WEB-011 assertions.

### Fieldora media identity and project association certification — run #26

Result: SUCCESS (run `32899441458`, job `97969558972`).

- PostgreSQL 16 service initialized successfully.
- Ruff governed-media identity and Project-association check passed.
- Reference/SQLite canonical identity tests passed.
- Browser certification proves byte-identical uploads in Project A/B use one media ID, create two Project associations, remain visible/downloadable in both linked Projects, and are absent/404 in an unlinked Project.
- PostgreSQL certification proves one organization-canonical media row plus two distinct persisted Project association rows, with target-scoped lookup returning only the linked canonical media ID.
- Zero-trust web certification on the same code head also passed; broader server-web and Platform server lanes were still in progress when this result was recorded.

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
