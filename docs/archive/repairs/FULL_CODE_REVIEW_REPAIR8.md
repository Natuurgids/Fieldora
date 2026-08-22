# Repair 8 architectural correction

Repair 8 implements the full-audit lifecycle changes rather than another runtime repair guard.

## Invariants

- A missing or empty selected directory is initialized in a sibling staging directory.
- The staged library is migrated, closed, reopened, schema-checked, identity-checked, and only then atomically renamed into place.
- `library.json` is written last inside staging, so a published manifest denotes a completed database.
- Existing libraries are opened strictly. Normal startup never migrates, deletes, moves, replaces, or rebuilds an existing database.
- Runtime schema checks are validation-only and cannot write or repair.
- Application-data and library roots must be separate and non-nested.
- The Windows installer recreates the Conda environment by default and creates the default library beside, not inside, `ApertureData-V4`.
- Observation statistics loading is deferred until after `MainWindow` construction and a failure is logged without aborting Qt object construction.

## Recovery

Recovery of an old, corrupt, partial, or incompatible library is intentionally not automatic. Such a library is refused without mutation. Any future recovery command must be explicit, preserve the source, and operate before normal startup.
