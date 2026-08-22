# Phase F administrator runbook

## Before deployment

- Validate the production declaration with `fieldora-deployment-assessment`.
- Verify image digest, release manifest, SBOM, migrations, backup, rollback target,
  external-secret references, TLS chain, and trust roots.
- Confirm at least two API and worker instances span zones and disruption budgets are
  active.

## Rolling upgrade

1. Freeze schema-destructive changes; take and verify a recovery point.
2. Deploy one canary API and worker with no reduction in current capacity.
3. Run status, authentication, PBAC denial, upload, search, job, and export probes.
4. Roll remaining replicas one zone at a time while watching errors and lease fencing.
5. Rebuild projections only through a new index and atomic alias switch.
6. Record the rollout exercise artifacts and release digest.

Rollback immediately if authorization behavior, schema compatibility, error budget,
worker fencing, or recovery objectives regress.

## Recovery

- Restore PostgreSQL to a new target time and verify consistency before promotion.
- Restore versioned objects without bypassing retention or legal holds.
- Rebuild OpenSearch from authoritative repositories; never treat it as the source.
- Rotate credentials exposed to the failed environment.
- Run the complete disclosure-denial probe before reopening ingress.

## Routine operations

Review quotas, usage, cost attribution, retention candidates, active legal holds,
secret age, failed jobs, audit continuity, backup verification, and outstanding Phase
F exercises. A configured topology is not a certified topology.

See [external-secret-rotation.md](external-secret-rotation.md) for conflict-safe,
metadata-only secret rotation through the shared production registry.

See [security-audit-export.md](security-audit-export.md) for tenant-scoped exports
that fail closed unless the authoritative audit hash chain verifies.

Use `fieldora-phase-f-certification plan` before live exercises and
`fieldora-phase-f-certification status` after evidence capture. A conditional result
is expected until all nine exercises pass in one environment.
