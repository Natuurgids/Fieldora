# Build 26 Repair 3 — code review and verified repairs

## Scope reviewed

The review covered the packaged Python source, all 25 core SQLite migrations, library creation/open/recovery, desktop bootstrap composition, Windows installation and launcher generation, install verification, release-manifest generation, and the complete packaged test suite.

## Confirmed root cause class

Startup trusted `schema_migrations` more strongly than the physical schema consumed by repositories. A database could therefore carry a complete-looking migration ledger while a required table or column was absent. The lifecycle also returned the short-timeout validation connection factory to the desktop instead of rebuilding a production factory after validation. Finally, installation smoke tests checked imports and entry points but did not create, reopen, and query a clean library.

## Repairs

- Build the canonical schema contract from all migrations and validate every required table and column.
- Compile representative repository queries, including `SELECT 1 FROM observations LIMIT 0`, before the desktop is constructed.
- Validate identity and `PRAGMA quick_check` on the same database path and production connection factory handed to repositories.
- Reconstruct empty incomplete libraries even when the migration ledger claims completion.
- Preserve refusal of unsafe in-place repair when an incomplete database contains user data.
- Extend installed-package verification to create, query, close, reopen, and query a temporary library.
- Add regression tests for a deliberately dropped `observations` table with an unchanged migration ledger.

## Validation performed

- 186 tests passed; one Qt scheduling test was skipped because PySide6 is unavailable in the Linux build container.
- Every Python file under `src`, `scripts`, and `tests` compiled successfully.
- A clean installed-source library was created with 25 migrations, passed SQLite `quick_check`, queried `observations`, and reopened successfully.
- The release manifest was regenerated and verified after a fresh archive extraction.

## Remaining platform limitation

The Windows GUI executable and PowerShell wrapper cannot be launched natively in this Linux build container. The package therefore includes stronger Windows-side install verification that performs the database lifecycle check inside the actual `natureai-next` Conda environment during installation.
