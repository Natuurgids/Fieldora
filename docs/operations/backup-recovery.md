# Fieldora Backup & Recovery

## Fieldora multi-server production recovery

Phase F production deployments must customize and validate
`deployment/reference-recovery.json`:

```text
fieldora-recovery-assessment deployment/reference-recovery.json --report recovery-assessment.json
```

The contract requires a recovery-point objective of at most five minutes and a
recovery-time objective of at most one hour, verified immutable PostgreSQL base
backups, continuous WAL archiving, encrypted recovery points, S3-compatible object
versioning and cross-zone replication, checksummed inventories, external recovery-key
custody, and non-destructive restore drills. Legal holds and delete markers must
survive recovery. OpenSearch is rebuilt from authoritative repositories and activated
through an atomic alias switch.

Passing the configuration assessment does not certify recovery. The point-in-time and
zone-failure exercises must still produce verified Phase F evidence from the same
production-equivalent environment.

## Fieldora one-node server recovery

Fieldora 0.08.24 provides a separate, non-destructive operator workflow:

```text
fieldora-server-recovery backup --data-root D:\FieldoraServer --destination E:\Backups\fieldora-server.zip
fieldora-server-recovery verify --source E:\Backups\fieldora-server.zip
fieldora-server-recovery restore-to-new-root --source E:\Backups\fieldora-server.zip --destination D:\FieldoraRecoveryTest
fieldora-server-recovery validate-restored-root --data-root D:\FieldoraRecoveryTest --output E:\Backups\readiness.json
```

The bundle contains online-consistent copies of all SQLite subsystem databases and
local governed media/export objects. Every file is size- and SHA-256-verified and every
database passes `PRAGMA integrity_check`. Restore refuses an existing destination, so
recovery drills never overwrite the source server. S3-compatible objects, TLS keys,
certificates, export-signing keys, and institutional trust material are listed in the
manifest but must be protected and restored through their owning provider.

The final validation opens the recovery copy through the current server adapters,
applies supported schema migrations, requires all authoritative Phase D databases,
reruns integrity checks, composes the API without listening on a network port, and
writes an atomic readiness report. It does not mutate the original server root.

Fieldora includes a separate **Fieldora Backup & Recovery** program, available from
the desktop and the Fieldora Start-menu folder. Compatibility links from older
Aperture installations may still open the same companion application.

## Back up a library

1. Open **Fieldora Backup & Recovery**.
2. Select **Back Up Library…**.
3. Choose a destination.
4. Fieldora creates a transaction-consistent SQLite backup and checksum manifest.

## Restore a library

1. Open **Fieldora Backup & Recovery**.
2. Select **Restore Library…** and choose a verified backup.
3. Read the warning: Fieldora will close, the database will be restored, and Fieldora will restart.
4. Approve the restore.

The companion asks a running Fieldora window to close cleanly, creates an emergency
pre-restore backup, validates the selected backup and restored SQLite database,
performs the replacement, and restarts Fieldora. Users do not run PowerShell.

If validation or replacement fails, the previous database is restored from the
rollback copy and Fieldora reports the failure.

Original photographs are not modified by database backup or restore.

## Backup history management

The standalone **Fieldora Backup & Recovery** application lists verified backups for
the selected library. Select an entry to verify it again, restore it, or delete the
database backup together with its checksum manifest. Restoration still creates an
emergency backup, closes Fieldora cleanly, validates the selected database, and
restarts Fieldora after success.

## Visible restore progress

During restore, Fieldora Maintenance Center remains open and reports each stage. When
**Back Up and Restore** is selected, the emergency backup is created and verified
before Fieldora closes. Restore results are written to the Fieldora log folder as
`restore-history.jsonl`.
