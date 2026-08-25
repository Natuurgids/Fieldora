# Fieldora web parity live status

Last updated: 2026-08-25

Read this file together with:

- `WEB_DESKTOP_PARITY_PLAN.md` — full 60-item work breakdown and acceptance contracts.
- `WEB_PARITY_IMPORT_CONTRACT.md` — detailed import/evidence identity source trace and target architecture.

This file is deliberately short. It is the current-session handoff/status board and should be updated whenever a slice changes state.

## Current branch state

Branch: `feature/versioned-facility-floorplans`

The Windows 11 + Docker Desktop clean installation has been runtime-validated by the user and the Rocky Linux 9 application image was built successfully. Runtime use then exposed desktop/web functional divergence; this program addresses that divergence.

## In progress

| Work | State | Current evidence / next action |
|---|---|---|
| WEB-006 authoritative duplicate-flow trace | DONE (analysis) | Source trace is recorded in `WEB_PARITY_IMPORT_CONTRACT.md`. Desktop uses production `ImportService.plan()/execute()`; browser currently implements a separate upload loop. |
| WEB-007 canonical evidence identity | BUILDING | Same organization + same project + same verified SHA-256/size now converges to one media identity in filesystem/SQLite and PostgreSQL metadata paths. Cross-project canonical identity remains WEB-011. |
| WEB-008 exact duplicate no-op | BUILDING | `GovernedMediaStore` now returns the existing media record for a repeated verified upload in the same context and removes the redundant temporary/object bytes. Dedicated certification is being repaired/rerun. |
| WEB-012 dedup race safety | BUILDING | PostgreSQL completion uses transaction-scoped advisory serialization around content identity. SQLite/reference concurrency still needs an explicit race test/transaction strategy. |
| WEB-015 reproduce multi-file browser fetch failure | ANALYSIS | Confirmed browser uses 4 MiB chunks; regular and staged APIs allow up to 8 MiB and the HTTP adapter has no smaller obvious body cap. Need a real managed-server Playwright request trace before changing behavior. |
| WEB-011 project link on existing evidence | READY | `media_links.py` already models organization-owned media plus project/collection/etc. associations. It is not yet wired into the main media upload/list path; do not broaden hash identity across projects until visibility/link semantics are wired. |

## Commits in the first evidence-identity slice

- `2831150daf9b708a1d84ecb01be177bbb12a82dc` — PostgreSQL same-context canonical content completion.
- `d810b803e74a0511798ed9f67a21e066f4875b3f` — governed media store returns canonical record and removes redundant bytes.
- `70a94bc50ea18b5ebed8f9ebac62cebced31ee14` — filesystem/reference identity tests.
- `9193475a819d2dfd22d968e98e4815a375232d03` — PostgreSQL identity test.
- `9512eb699728109df188402a66d5792f06bd3694` — dedicated media identity certification workflow.
- `9789297c9645f2103d8d14fd95c7a299d020cce0` — repair PostgreSQL advisory key after run #1 exposed illegal NUL separators.

## Certification history

### Fieldora media identity certification — run #1

Result: FAILED usefully.

- Ruff passed.
- 3 filesystem/reference tests passed.
- PostgreSQL test failed before exercising identity logic because the advisory lock key contained NUL separators, which PostgreSQL text parameters reject.
- Commit `9789297c9645f2103d8d14fd95c7a299d020cce0` replaces that key with SHA-256 hex text.
- A fresh run on/after that commit must be green before WEB-007/008 PostgreSQL work is marked DONE.

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
4. Inspect the current branch head and latest workflow runs before editing.
5. Finish any `BUILDING` item before starting unrelated parity work unless a failed test shows the design is wrong.
6. Update this status file when the slice changes state.
