# Retention and legal holds

Production maintenance uses `fieldora-retention --backend postgresql` with a
DSN file supplied by the external-secret provider. Standalone deployments can use the
SQLite backend.

Registering a retention deadline does not itself delete data. Workers claim a bounded
set of due records, remove the corresponding authoritative object through its governed
service, and complete the record with the same worker identifier and fencing token.
A stale worker cannot complete work reclaimed after lease expiry.

Legal holds may cover an organization, resource type, or individual resource. They are
excluded inside the same transaction that claims due work; workers cannot receive held
records. Hold reasons may contain sensitive legal information and must not be included
in general usage reports.

Example organization-wide hold:

```text
fieldora-retention --backend postgresql --postgres-dsn-file /run/secrets/postgresql-dsn \
  hold-place --hold-id case-2026-17 --organization tenant-a \
  --reason "Preservation order" --created-at-epoch 1785369600
```

Releasing a hold is explicit and timestamped. Deletion should only be completed after
the governed payload service confirms physical removal; otherwise let the lease expire
for safe retry.
