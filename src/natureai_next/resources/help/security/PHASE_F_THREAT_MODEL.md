# Phase F production threat model

## Protected assets

Fieldora protects tenant records, media objects, search projections, governed exports,
audit events, credentials, signing keys, encryption keys, backups, and recovery
material. Tenant and project boundaries remain authoritative during normal operation,
maintenance, failover, recovery, and upgrade.

## Trust boundaries

- Public clients cross TLS ingress before reaching an API.
- APIs and workers cross authenticated TLS boundaries to PostgreSQL, object storage,
  search, identity, and external-secret providers.
- Operators cross a separately authenticated administration boundary.
- Backup and exercise artifacts cross an offline verification boundary before use.

## Principal threats and controls

| Threat | Required control |
|---|---|
| Direct object or search access | Private endpoints; API-only disclosure; PBAC filtering |
| Tenant confusion | Organization scope in every repository and governance decision |
| Forged or replayed work | Idempotency keys, renewable leases, and fencing tokens |
| Credential disclosure | External secret references only; bounded rotation; no inline values |
| Compromised node | Least privilege, network policy, immutable image, rapid rotation |
| Failover authorization gap | Same policy repository and tests on every replica |
| Backup disclosure | Encrypted immutable backups with separate key custody |
| Audit tampering | Canonical hash chain and integrity-addressed tenant export |
| Retention defeating a hold | Durable legal-hold exclusion inside the claim transaction |
| Supply-chain substitution | Release manifest, SBOM, pinned ranges, scanning, signatures |

## Explicit residual risks

The source release cannot certify a provider topology. Availability, recovery time,
recovery point, zone isolation, certificate rotation, and penetration resistance stay
conditional until the Phase F exercise evidence is produced and independently
reviewed. Excalidraw remains offline and is not part of the platform trust boundary.
