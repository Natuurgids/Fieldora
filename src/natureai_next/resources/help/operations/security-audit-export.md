# Security audit export

Use `fieldora-audit-export` to create a tenant-scoped archive from Fieldora's
authoritative access-control audit repository. The command verifies the complete
hash chain before writing output. A missing chain record, broken predecessor, or
changed event fails the operation without leaving a destination archive.

Production:

```text
fieldora-audit-export --backend postgresql \
  --postgres-dsn-file /run/secrets/fieldora-access-dsn \
  export --organization ORGANIZATION_ID \
  --destination /secure/audits/ORGANIZATION_ID.zip
```

Standalone operation uses `--backend sqlite --database PATH`. The export is capped
at 10,000 newest source events per invocation, then filtered to the requested
organization. Choose a smaller `--limit` when required by the review scope.

Verify a received archive independently:

```text
fieldora-audit-export verify --source ORGANIZATION_ID.zip
```

Verification checks the exact archive members, payload digest, event count, tenant
boundary, format, and, for format version 2, the recorded source-chain verification
state. Legacy format-version-1 archives remain verifiable but do not attest that the
source repository chain was checked at creation. Store the archive
under the applicable retention and legal-hold policy. The archive contains audit
records and provider-neutral integrity metadata; it does not contain credentials.
