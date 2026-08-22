| **Release**  | 0.11.21 — AI review and offline map labels                  |
|--------------|------------------------------------------------------------------------------|
| **Audience** | System administrators, security administrators, data stewards, and operators |
| **Platform** | Windows 11 desktop; optional multi-server deployment                         |
| **Status**   | Operational reference — July 2026                                            |

**This manual reflects the packaged Fieldora 5.4.0 source release.
Commands that change data should first be exercised against a test
library or non-production environment.**

## Trash and deletion approvals

Local trash remains available for removing accidental, private or non-company
material before organizational processing. Permanent organizational deletion is
requested from **Trash & Deletion Approvals** and assigned to either a named
identity or organization function.

If that target is unavailable, Fieldora assigns another enabled administrator
in the organization. If the requester is the only administrator, the request
falls back to that sole administrator. If no configured administrator exists,
the tool-administrator identity owns the queue. Requesters cannot approve their
own request when an independent approver is assigned. Requests, routing and
decisions are audited and included in backup.

## Calendar-provider boundary

The packaged integration exports standard iCalendar files and opens explicit
Google Calendar or Outlook event-composer URLs. It has no background provider
token and performs no automatic synchronization. Deploying two-way sync requires
separate Google Calendar API or Microsoft Graph OAuth registration, administrator
consent, encrypted token retention, access policy, audit and conflict handling.

## Marine and maritime administration

Marine & Freshwater Science and Maritime Operations are independently controlled
under **Enabled Modules**. Turning either off hides its navigation and screens;
it does not delete `marine-maritime.sqlite3`, attachment links or audit events.
Include that subsystem database in backup, recovery and integrity checks. Export
of linked media remains subject to Fieldora access contracts.

AI review assignments are auditable workflow metadata. Use identity IDs from
Access & Contracts, assign reviewer roles and PBAC permissions separately, and
do not treat assignment itself as authorization. Disabling a Library type
hides its review surface and cancels active analysis without deleting retained
evidence, decisions, or assignment history.

# How to use this manual

Follow procedures in order. Text marked Important identifies a safety or
security boundary. Command blocks are intended to be copied only after
paths, environment names, and organization identifiers are replaced.

# Contents

- 1\. Administrative model and responsibilities

- 2\. Architecture and trust boundaries

- 3\. Standalone library administration

- 4\. Production topology

- 5\. Identity, PBAC, contracts, and approvals

- 6\. PostgreSQL repositories

- 7\. Object storage and exports

- 8\. OpenSearch projection

- 9\. OIDC federation

- 10\. Quotas, usage, and cost reporting

- 11\. Retention and legal holds

- 12\. External-secret rotation

- 13\. Security audit export

- 14\. Backup, restore, and disaster recovery

- 15\. Health, workers, and rolling upgrades

- 16\. Phase F certification

- 17\. Incident response

- 18\. Routine operations

# 1. Administrative model and responsibilities

| **Role**               | **Primary responsibility**                                                         |
|------------------------|------------------------------------------------------------------------------------|
| Library administrator  | Create, verify, back up, restore, and maintain standalone libraries                |
| Security administrator | Identity mapping, PBAC policy, contracts, approvals, audit, and secret references  |
| Platform operator      | API, workers, PostgreSQL, object storage, search, ingress, rollout, and monitoring |
| Data steward           | Retention deadlines, legal holds, exports, taxonomy, and disclosure review         |
| Certification operator | Execute live exercises and record attributable provider evidence                   |

**Important:** Separate duties in production. The ability to operate
infrastructure must not automatically grant permission to disclose
tenant records or alter contracts.

# 2. Architecture and trust boundaries

- Authoritative records live in selected SQLite or PostgreSQL
  repositories.

- Media and governed export bytes remain behind contained filesystem or
  S3-compatible object-store boundaries.

- OpenSearch is a rebuildable projection; every candidate is still
  filtered through PBAC.

- Workers use bounded leases and fencing tokens so stale processes
  cannot publish completion.

- Secrets remain in external providers. Fieldora stores only approved
  provider references and rotation state.

- Standalone Excalidraw documents are local files under
  Documents/Whiteboards and make no network requests.

## Data classification

- Credentials and DSNs: secrets; never place in ordinary configuration,
  logs, archives, or command arguments.

- Audit, contracts, holds, and identity mappings: security-sensitive
  authoritative records.

- Original media and observations: research records subject to
  organizational policy.

- Search indexes, thumbnails, and caches: derived data; rebuildable but
  still potentially sensitive.

- Release manifests, SBOMs, and evidence plans: operational metadata;
  preserve integrity.

# 3. Standalone library administration

natureai-next-admin library-create D:\Fieldora-Library --name
"Institution Library" --locale en

natureai-next-admin library-check D:\Fieldora-Library --full

- Keep the library on a local filesystem suitable for SQLite locking.

- Use application backup commands or coordinated copies; never copy live
  databases ad hoc.

- Test restoration into a new path.

- Protect library, backup, and export paths with least-privilege
  filesystem ACLs.

- Review free space for originals, thumbnails, caches, models, and
  temporary exports.

# 4. Production topology

A configuration-ready Phase F topology contains redundant zonal API
replicas, continuous fenced workers, PostgreSQL failover and PITR,
replicated encrypted object storage, distributed OpenSearch, TLS
ingress, external secret rotation, and zero-unavailable rolling
upgrades.

fieldora-deployment-assessment deployment/reference-production.json

**Important:** Configuration-ready does not mean certified.
Certification requires all nine live exercises to pass in one
environment.

- Pin container images by independently verified digest.

- Replace example hostnames and endpoints through an environment
  overlay.

- Provision runtime secrets through the external provider.

- Use private PostgreSQL, S3-compatible, and OpenSearch endpoints.

- Treat emptyDir volumes as staging only, never as authoritative
  storage.

# 5. Identity, PBAC, contracts, and approvals

- Create explicit human, service, and device identities.

- Map federated issuer/subject pairs to enabled local identities.

- Assign roles and groups deliberately; provider claims do not become
  permissions.

- Use PBAC policies for action, resource, organization, project,
  purpose, field, condition, and time constraints.

- Keep proposed contracts non-authorizing until required approvals are
  complete.

- Review expiring contracts and approval queues.

- Verify deny behavior before and after every policy change.

# 6. PostgreSQL repositories

| **Repository**               | **Configuration intent**                                     |
|------------------------------|--------------------------------------------------------------|
| Access                       | --access-backend postgresql and --postgres-access-dsn-file   |
| Science                      | --science-backend postgresql and --postgres-science-dsn-file |
| Jobs                         | --job-backend postgresql and --postgres-jobs-dsn-file        |
| Media metadata               | --media-metadata-backend postgresql and DSN file             |
| Export metadata              | --export-metadata-backend postgresql and DSN file            |
| Governance/retention/secrets | Use the corresponding operator CLI with --backend postgresql |

- Use dedicated database roles and service-account-readable DSN files.

- DSN files are bounded to 16 KiB and should contain only the connection
  string.

- Selecting PostgreSQL creates compatible schemas but does not silently
  migrate SQLite data.

- Test failover, connection pool behavior, backups, PITR, and
  restore-to-new-target before production.

# 7. Object storage and exports

fieldora-server --media-object-store s3 --s3-bucket research-media
--s3-prefix institution-a/media --s3-region eu-central-1 serve

- Deny public bucket access.

- Use the SDK credential provider chain; do not pass access keys on the
  command line.

- Enable versioning, encryption, cross-zone replication, inventory, and
  checksum verification.

- Keep media and export prefixes separate.

- Revocation, expiry, contract terms, and selected-element permissions
  apply before bytes are disclosed.

# 8. OpenSearch projection

fieldora-server --search-backend opensearch --opensearch-endpoint
https://search.example --opensearch-index fieldora-search
--opensearch-bearer-token-file D:\FieldoraSecrets\search.token serve

- Require HTTPS without credentials in the URL.

- Keep bearer tokens outside the data root.

- Rebuild into a new concrete index and switch the alias atomically.

- Bound queries and result sizes.

- Never use search documents as authoritative evidence or bypass PBAC.

# 9. OIDC federation

fieldora-server serve --oidc-issuer https://identity.example
--oidc-audience fieldora --oidc-discovery --oidc-refresh-seconds 3600

- Pin issuer and audience.

- Use HTTPS discovery or a trusted local JWKS, never both.

- Map every provider subject explicitly.

- Test unknown-key refresh, disabled mappings, expired tokens, incorrect
  audience, and deny behavior.

- Plan emergency local administration before relying on federation.

# 10. Quotas, usage, and cost reporting

fieldora-governance --backend postgresql --postgres-dsn-file
governance.dsn quota-set --organization ORG --metric jobs --limit 1000
--period-seconds 86400

fieldora-governance --backend postgresql --postgres-dsn-file
governance.dsn usage-report --organization ORG --start-epoch 0
--end-epoch 2000000000 --unit-costs rates.json

- Use expected revisions when changing existing quotas.

- Treat usage reports as tenant-scoped.

- Supply decimal unit costs as strings to avoid binary floating-point
  rounding.

- Alert on repeated quota denial and unexpected cost growth.

# 11. Retention and legal holds

fieldora-retention --backend postgresql --postgres-dsn-file
retention.dsn register --organization ORG --resource-type export
--resource-id ID --expires-at-epoch EPOCH

fieldora-retention --backend postgresql --postgres-dsn-file
retention.dsn hold-place --hold-id HOLD --organization ORG --reason
investigation --created-at-epoch EPOCH

- Holds may apply organization-wide, by resource type, or to a specific
  resource.

- Claims exclude active holds in the same transaction.

- Multiple workers use SKIP LOCKED and incrementing fence tokens.

- Completion is valid only for the claiming worker and current token.

- Never release a legal hold without documented authority.

# 12. External-secret rotation

fieldora-secret-rotation --backend postgresql --postgres-dsn-file
rotation.dsn stage --purpose oidc-signing --version-id 2026-07
--provider-reference vault://fieldora/oidc/2026-07 --created-at-epoch
EPOCH

fieldora-secret-rotation --backend postgresql --postgres-dsn-file
rotation.dsn activate --purpose oidc-signing --version-id 2026-07
--expected-active-version 2026-04 --activated-at-epoch EPOCH

- Create and validate the provider secret first.

- Fieldora accepts Vault, KMS, or external-secret references, never
  secret values.

- Activation is serialized per purpose.

- An active_version_conflict means another operator changed state;
  inspect status before retrying.

- Verify workload reload and functional behavior after activation.

# 13. Security audit export

fieldora-audit-export --backend postgresql --postgres-dsn-file
access.dsn export --organization ORG --destination ORG-audit.zip

fieldora-audit-export verify --source ORG-audit.zip

- The full source hash chain must verify before export.

- Events are filtered by the organization recorded in each authorization
  request.

- New archives include format-version-2 source-chain attestation.

- Legacy version-1 archives remain verifiable but do not attest
  source-chain checking.

- Store exports under retention and legal-hold policy.

# 14. Backup, restore, and disaster recovery

- PostgreSQL: verified immutable base backups, continuous WAL archiving,
  restore-to-new-target drills, integrity checks, and a five-minute RPO
  objective.

- Objects: versioning, checksummed inventory, cross-zone replication,
  deletion-state recovery, and legal-hold preservation.

- Search: rebuild from authoritative repositories and switch aliases
  atomically.

- Keys: external custody with tested recovery access.

- Target Phase F RTO: one hour or less, subject to the validated
  recovery contract.

1.  Declare incident and stop risky writes where appropriate.

2.  Select a verified recovery point.

3.  Restore to a new target; do not overwrite the only surviving copy.

4.  Run database and object integrity checks.

5.  Rebuild search projections.

6.  Rotate credentials exposed to the failed environment.

7.  Run authentication, PBAC denial, media, search, job, export, and
    tenant-isolation probes.

8.  Reopen ingress only after approval.

# 15. Health, workers, and rolling upgrades

- Desktop batch-analysis screens submit up to four selected files concurrently.
  Size server worker capacity, provider rate limits, and GPU/CPU memory for the
  number of simultaneously active Photos, Sounds, Videos, and Documents
  screens.

- **Settings → Turn Workspaces On or Off** is also the analysis activation
  boundary. Disabling a media library hides its analysis screen, disables new
  submissions, and requests cancellation of unfinished items. It does not
  delete completed enrichment or historical results.

- Liveness reports process health and should not depend on providers.

- Readiness checks PostgreSQL, object storage, and search and removes
  unhealthy replicas from service.

- On SIGTERM, API replicas become unready, drain, and close cleanly.

- Workers stop claiming new jobs and finish the active fenced job.

- Use stable unique worker IDs and suitable lease/grace periods.

9.  Take and verify a recovery point.

10. Deploy a canary without reducing capacity.

11. Run status, auth, PBAC denial, upload, search, job, and export
    probes.

12. Roll one zone at a time.

13. Watch errors, readiness, leases, and fence tokens.

14. Rollback immediately on authorization, schema, error-budget,
    fencing, or recovery regression.

# 16. Phase F certification

fieldora-phase-f-certification plan --environment ENV --destination
phase-f-plan.json

fieldora-record-phase-f-evidence EXERCISE --evidence-root
deployment\evidence --environment ENV --executed-at-utc TIME --result
passed --objective TEXT --observed TEXT --artifact provider.log
--operator NAME

fieldora-phase-f-certification status --environment ENV --evidence-root
deployment\evidence --report status.json

| **Required exercise**       | **Proof focus**                                                  |
|-----------------------------|------------------------------------------------------------------|
| API and worker node loss    | Traffic continuity; readiness; fenced completion                 |
| PostgreSQL failover         | Writable new primary; committed data; readiness recovery         |
| Object and search node loss | Checksums/range reads; alias/query/PBAC behavior                 |
| Certificate rotation        | New trusted chain; no plaintext fallback                         |
| Upgrade and rollback        | Availability, draining, compatibility, prior release restoration |
| PITR and zone failure       | RPO/RTO, integrity, surviving capacity, tenant isolation         |

**Important:** Do not record a passing result from configuration
inspection. Evidence must come from the live exercise and one consistent
environment identifier.

# 17. Incident response

- Preserve evidence and establish an incident commander.

- Contain access without destroying logs or legal-hold data.

- Identify affected organizations, resources, identities, and time
  ranges.

- Export and verify tenant audit records.

- Rotate exposed credentials through the external provider.

- Recover to new targets when integrity is uncertain.

- Document decisions, observed facts, and notification obligations.

- Run lessons learned and convert corrective work into tracked changes.

# 18. Routine operations

| **Frequency** | **Review**                                                                                  |
|---------------|---------------------------------------------------------------------------------------------|
| Daily         | Readiness, failed jobs, storage capacity, backup/WAL status, security alerts                |
| Weekly        | Quota denials, usage anomalies, expiring contracts, pending approvals, retention candidates |
| Monthly       | Legal holds, secret age, audit continuity, restore sample, dependency/SBOM review           |
| Quarterly     | PITR drill, access review, certificate rotation readiness, rollback exercise                |
| Each release  | Manifest/digest, backup, canary, security probes, evidence status, rollback target          |
