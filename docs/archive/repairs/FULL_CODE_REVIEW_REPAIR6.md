# Build 26 Repair 6 — Repository Connection Boundary Fix

## Confirmed failure

The previous repairs validated the library lifecycle and added a pre-window schema check, but repositories retained a plain `SqliteConnectionFactory`. The observation statistics workspace therefore still had a connection path that was not guarded at the exact moment the query connection was opened.

## Repair

`RuntimeGuardedConnectionFactory` now wraps the production factory immediately after the library context opens. Every repository connection:

1. invokes the lifecycle runtime schema guard;
2. opens the canonical database path;
3. compiles `SELECT 1 FROM observations LIMIT 0` on that exact connection;
4. closes, revalidates, and retries once if the database changed between validation and connection creation.

The lifecycle callback uses an independent unguarded factory, avoiding recursion.

## Regression coverage

Tests cover both normal guarded reads and replacement of a previously valid database immediately before the first repository query. The complete suite passes in the build environment; the Qt-only scheduling test remains skipped because PySide6 is unavailable there.
