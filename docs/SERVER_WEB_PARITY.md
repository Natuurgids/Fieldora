# Fieldora server web parity

The server web client uses the same six workspaces as the offline V5 client: Home,
Library, Observations, Research, Knowledge & AI, and Administration. It is a thin
client over the governed `/api/v1` boundary; it does not open desktop SQLite files.

## Browser coverage

| Server capability | Web workspace | PostgreSQL-capable authority |
| --- | --- | --- |
| Password session, logout, current identity | Login | Access control |
| OIDC bearer session | Login, Organization OIDC | Access control |
| Liveness, readiness, backend profile | Home, Administration | Readiness checks every selected PostgreSQL DSN |
| Projects, dossiers, collections | Research | Science |
| Observations and measurements | Observations | Science |
| Identification/enrichment records | Knowledge & AI | Science |
| PBAC-filtered full-text search | Knowledge & AI | Science source plus OpenSearch projection when selected |
| Governed media list, resumable upload, authenticated download | Library | Media metadata; S3 optional for bytes |
| Staged submissions: create, append, seal, process | Library, advanced import | Job queue is PostgreSQL-capable; quarantine ledger remains node-local SQLite |
| Export job, job state, authenticated download, attestation, revocation | Research, Administration | Jobs and export metadata |
| Contracts, approval queue, expiry, lifecycle | Administration | Access control |
| Device code creation, approval, token exchange | Administration | Access control |
| Audit events and hash-chain verification | Administration | Access control |
| Tenant quota consumption/runtime status | All requests, Administration | Governance |

The runtime card reports the actual selected backend for access, Science, media
metadata, jobs, export metadata, governance, search, and object storage. This makes a
mixed or incomplete PostgreSQL deployment visible rather than presenting it as a
fully shared server.

## Deliberately operator-only functions

Bootstrap and recovery commands are not browser buttons. Initial-user creation,
service-key lifecycle, direct device-key creation, OIDC identity mapping, export key
creation and verification, recovery assessment, secret rotation, audit export, worker
supervision, and destructive retention execution remain CLI/operator workflows. This
preserves a usable recovery path when the web tier or identity provider is unavailable
and avoids exposing root-of-trust operations through the normal application session.

## PostgreSQL boundary

Access control, Science records, media/upload metadata, jobs, export metadata, and
tenant governance have PostgreSQL repository implementations. The Kubernetes
reference deployment selects all six and makes PostgreSQL readiness part of
`/api/v1/health/ready`.

Media and export bytes are not stored in PostgreSQL; use S3-compatible object storage
for multi-node deployments. Search is a rebuildable projection and can use OpenSearch.
The staged-ingestion quarantine ledger and files remain node-local, so API and worker
processes handling a submission must share the quarantine volume. This is the one
server workflow that is not currently safe to distribute across unrelated nodes.

