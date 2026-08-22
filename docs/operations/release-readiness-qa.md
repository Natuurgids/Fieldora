## V3.RC1 release identity checks

Confirm VERSION, pyproject.toml, package `__version__`, About, release notes, embedded Help, manifest, and archive name all identify 3.0.0rc1.post2 / V3.RC1.

# Version 1 Release-Readiness QA

This checklist supplements automated tests. Complete it on the supported Windows 11 reference system before declaring a release candidate.

## Library lifecycle

1. Create a new library on a local NTFS volume.
2. Close and reopen it after a clean shutdown.
3. Simulate an interrupted process and confirm the library lock and WAL recovery behavior.
4. Run both normal and full Health Center checks.

## Representative workflow

1. Import supported photographs, including duplicates and one damaged file.
2. Browse thumbnails and full previews.
3. Edit ratings, labels, notes, taxonomy, location, and observations.
4. Search and create a saved collection.
5. Run available local AI generation and review suggestions.
6. Export originals, derivatives, and metadata.
7. Confirm the source library is unchanged by export.

## Backup and recovery

1. Create and verify a backup from the UI.
2. Tamper with a copy and confirm verification rejects it.
3. Stage a restore, close Aperture, and run the recovery script.
4. Reopen the restored library and run a full Health Center check.
5. Confirm the emergency backup and rollback path exist.

## Offline update

1. Configure a local folder, USB path, mapped drive, and permitted UNC share.
2. Reject an older, incompatible, path-escaping, or checksum-invalid package.
3. Stage a valid update only after the verified pre-update backup succeeds.
4. Install after exit, reopen, and run a full Health Center check.
5. Exercise rollback by simulating replacement failure.

## Accessibility and UI

- Complete primary workflows using keyboard only.
- Verify accessible control names with Windows Narrator.
- Test 100%, 150%, and 200% display scaling.
- Confirm focus visibility, dialog ordering, and error-message readability.

## Performance and soak

- Measure startup and first-page display with representative 10,000- and 100,000-asset libraries.
- Run a multi-hour browse/import/AI workload while observing memory growth and UI responsiveness.
- Record backup, restore, search, and update-staging timings.
- Confirm background work can be cancelled or recovered at documented safe checkpoints.

Record hardware, data size, timings, failures, and deviations in `VALIDATION.md`.

## Documentation freeze acceptance

- Source documentation and packaged offline Help contain the same guide set.
- Help includes Roadmap & Future Releases and the Version 1 Project Handover.
- Roadmap assignments are: Version 2 taxonomy/library/provenance/hashing; Version 3 advanced analysis/collaboration; Version 4 offline maps/calendar/field intelligence/time-lapse; Version 5 semantic search and discovery.
- User-facing terminology distinguishes Aperture, the internal NatureAI_Next engine, and BioCLIP.
- Version 1 intentional limitations are documented rather than implied to be defects.
- The documentation build introduces no runtime or database migration.
