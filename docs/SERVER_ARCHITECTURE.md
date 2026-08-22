# Fieldora Reference Server Architecture

## Status

Fieldora 0.08 adds the first executable governed server slice. It is a one-node
reference implementation for controlled trials, not a production internet deployment.

## Request boundary

The `fieldora-server` command exposes `/api/v1`. Login exchanges a local username and
password for a high-entropy opaque bearer token. Only a SHA-256 token digest is stored.
Sessions expire, can be revoked, and are rechecked against the enabled identity on every
request. Password verifiers use PBKDF2-HMAC-SHA256 with a unique 256-bit salt.

Automations use service identities and one-time-disclosed API keys. Only the key prefix
and SHA-256 digest are stored. Each authentication checks expiry, revocation, identity
kind, and enabled state; possession of a key grants no rights by itself because the
resulting request still passes through PBAC.

Server deployments may select PostgreSQL for the complete access-control repository:
organizations, identities, credentials, sessions, federation mappings, groups, roles,
PBAC policies, contracts, approvals, and hash-chained audit. Concurrent audit appends
take a transaction-scoped advisory lock before allocating the sequence and predecessor
hash, preventing multiple API nodes from forking the chain. SQLite remains the
standalone default.

Field clients use the same hardened credential mechanism with an explicit device
identity. Enrollment assigns a role at organization/project scope, so the key cannot
escape the enrolled project even when another project exists in the same organization.
This is administrator-driven enrollment; interactive user-code device authorization
is also available: a device requests short-lived device/user codes, an authenticated
user with `enroll_device` permission approves the target project, and the device
exchanges its secret exactly once. Both codes are stored only as hashes.

Federated users may authenticate with an OpenID Connect JWT when the server is started
with a pinned issuer and audience plus either a local JWKS file or HTTPS discovery.
Discovery requires an exact issuer match, accepts only an HTTPS JWKS endpoint, bounds
metadata downloads, and caches keys for a configurable 60-to-86400-second interval.
An unknown key ID causes one immediate refresh for routine provider rotation.
Verification accepts only RS256, selects the declared key ID, verifies the signature
and issuer/audience/expiry/not-before claims, then maps `(issuer, subject)` to an
enabled local user. External claims never become permissions directly; local roles,
contracts, and PBAC remain authoritative.

Security-audit reads require a distinct `view_audit` PBAC decision, are bounded to 200
events, and are filtered to the caller's organization unless the caller is an explicit
platform administrator. Every response reports current SHA-256 chain verification.

Search uses the separate, rebuildable `server-search.sqlite3` FTS projection. Query
syntax is normalized and bounded, at most 500 internal candidates are considered, and
each candidate receives a `search` PBAC decision before its title or snippet enters the
response. Projection failure never falls back to an unfiltered Science query.

Server deployments may instead select an HTTPS OpenSearch-compatible projection.
Rebuilds write a fresh concrete index, atomically move the configured alias, and remove
only prior Fieldora-owned concrete indexes. Requests and responses are bounded,
cross-origin redirects and URL credentials are rejected, and an optional bearer token
is read from a file rather than a command argument. OpenSearch remains reconstructable
and non-authoritative; every candidate still crosses the same PBAC disclosure gate.

Background work is persisted in the authoritative `server-jobs.sqlite3` queue.
Independent workers claim jobs with explicit identities, expiring renewable leases,
unique fencing tokens, and bounded attempts. A superseded worker cannot commit a
terminal result after another worker reclaims its job. Submission and result reads are
separate PBAC actions; submitting a job does not automatically authorize its status or
output. Handlers perform deterministic search-projection rebuilds and governed
portable-project generation. SQLite remains the one-node queue adapter; multi-node
workers can select the PostgreSQL job adapter, which uses `JSONB`, `TIMESTAMPTZ`, and
one atomic `FOR UPDATE SKIP LOCKED` claim. This is the first PostgreSQL parity slice;
the other authoritative server repositories still use SQLite.

Completed project exports are registered independently in `server-exports.sqlite3`
and stored beneath a contained server-export root. Creating the job requires `export`
on the project, reading its job result requires `view_job`, and fetching the package
requires `download_export`; all three checks are evaluated independently. The API
returns an opaque export ID, expiry, size, and SHA-256, supports HEAD and byte ranges,
and never discloses a storage path. A separate `revoke_export` decision withdraws the
result and removes its bytes immediately. The `purge-expired-exports` maintenance
command removes expired payloads while retaining lifecycle timestamps in the registry.
Packages exclude original Library media.

Server deployments may place export lifecycle and attestation metadata in PostgreSQL.
Revocation and attestation attachment are conditional writes. Expiry maintenance
claims bounded batches with row locks and `SKIP LOCKED`, marks them purged
transactionally, and lets only the claiming worker remove payload bytes. Export files
remain beneath the contained export root in this slice.

`init-export-signing-key` explicitly creates one Ed25519 private identity beneath the
server data root and a separate public trust file. The command refuses to overwrite an
existing identity. When configured, the one-shot worker signs the SHA-256 of each
completed archive and stores the detached attestation with its export record.
`/api/v1/exports/{id}/attestation` requires the same `download_export` decision as the
archive. `verify-project-export` verifies both the complete archive digest and the
signature against a caller-selected trust file. Operators must back up the private key
separately and distribute only the public trust file.

`generate-export-recipient-key` creates an X25519 private key and a separately
shareable public JSON document. An export request may include that public document.
The worker first creates the ordinary portable ZIP, encrypts it with a fresh ephemeral
X25519 key plus HKDF-SHA256 and streaming AES-256-GCM, removes plaintext staging, and
registers only the encrypted result. `decrypt-project-export` requires the matching
private key and a new destination. If signing is enabled, the attestation covers the
encrypted bytes delivered by the API.

Trusted host administrators can create a project contract grant with
`create-project-contract`. The command accepts an explicit subject, organization,
project, UTC-capable start/end dates, and a comma-separated right list; it creates
narrow policies rather than a wildcard grant. `set-contract-status` can activate,
suspend, or terminate the contract, and the next PBAC decision immediately observes
that state.

Authenticated clients can administer contracts through:

- `POST /api/v1/admin/contracts`;
- `GET /api/v1/admin/contracts` with bounded cursor pagination;
- `GET /api/v1/admin/contracts/{id}`;
- `POST /api/v1/admin/contracts/{id}/status`.
- `POST /api/v1/admin/contracts/{id}/approve`.

Each operation evaluates `administer_contracts` for the target organization/project.
List candidates are filtered before disclosure, and denied object IDs are
indistinguishable from unknown IDs. Status changes immediately affect all policies
whose source is that contract.

Creation may request independent approval. Such a contract remains `proposed` without
policies. Approval uses the distinct `approve_contracts` PBAC action, rejects the
requesting identity, and atomically writes active status plus derived policies. The
web client enables this mode by default and presents Approve only for proposed
contracts; the server still enforces identity separation.

The limited web client presents Contracts as a separate accessible tab. It supports
bounded loading, creation with explicit rights, and lifecycle actions. It uses DOM
text nodes for returned values, keeps the bearer token in session storage, and marks
contract calls with the administration purpose. The client does not receive a trusted
administrator flag and cannot authorize itself.

Science queries are read through a replaceable projection boundary. The API evaluates
each candidate project or dossier through the central PBAC decision service. Records
that do not receive an allow decision are omitted. The web client has no database or
object-store access and receives no direct media URL.

Server deployments may select a PostgreSQL Science repository. JSONB records retain
stable collection/record identities and per-record revisions; snapshot-wide saves lock
the singleton revision and commit all inserts, updates, and removals atomically. API
reads/writes, search rebuilds, and project export workers use the same selected Science
source. Standalone clients continue to use the independent `science.sqlite3` database.

Project and dossier writes are also evaluated through PBAC using the `edit` action.
Clients may send `If-Match` with the current record revision; stale writers receive
HTTP 409 and no mutation is committed. Login attempts are bounded per client/username
window.

Governed media is copied beneath a contained server-media root and registered in the
independent `server-media.sqlite3` subsystem with organization, project, MIME type,
size, and SHA-256. `/api/v1/media/{id}` evaluates `download` permission before opening
the file, supports single HTTP byte ranges and HEAD, and never exposes a storage path.
Denied and unknown media use the same 404 response.

Server deployments may place governed-media and resumable-upload metadata in
PostgreSQL independently of object storage. The PostgreSQL adapter uses 64-bit sizes,
constrained digests, optimistic contiguous offsets, and a row lock for atomic upload
completion. Media bytes remain in the selected contained filesystem or S3-compatible
adapter, and all reads still cross the PBAC-gated API.

Fieldora 0.08.22 places finalized governed media behind an object-store contract.
Standalone installs retain the contained filesystem adapter. Server deployments may
select the optional S3-compatible adapter with bucket, opaque prefix, endpoint, and
region configuration. The adapter uses the SDK credential provider chain; credentials
are not accepted as command-line values. Database records retain opaque object keys,
not URLs. Uploads remain in contained local staging until their declared size and
SHA-256 are verified, after which publication and registry commit use compensating
deletion on failure. All reads still enter through the PBAC-gated media API.

Resumable uploads begin with declared project, filename, MIME type, byte count, and
SHA-256. The server persists the owner and exact received offset in the media database.
Each PUT chunk must be contiguous and no larger than 8 MiB. Only the creating identity
may continue the session, PBAC is re-evaluated for every chunk, and the temporary file
is atomically published only after size and digest verification.

`fieldora-server-recovery` creates a verified one-node recovery bundle using online
SQLite backups plus local governed media/export objects. Its exact manifest includes
size and SHA-256 for every file, and verification reruns SQLite integrity checks.
Restore is intentionally limited to a new data root. External S3 objects and private
TLS/signing material remain explicit provider-managed dependencies.

The restored-root validator then opens that isolated copy through all six current
server adapters, applies supported migrations, reruns integrity checks, composes the
API, and exercises its status boundary without binding a listener. Missing databases
are failures, not defaults. An optional JSON readiness report supports automated
upgrade and recovery gates.

## Run locally

```text
fieldora-server --data-root D:\FieldoraData init-user --organization institute-a --name "Research Manager" --username manager
fieldora-server --data-root D:\FieldoraData serve
fieldora-server --data-root D:\FieldoraData serve --oidc-issuer https://identity.example --oidc-audience fieldora --oidc-discovery --oidc-refresh-seconds 3600
fieldora-server --data-root D:\FieldoraData run-job-worker --worker-id worker-a --max-jobs 100 --lease-seconds 300
fieldora-server --data-root D:\FieldoraData --search-backend opensearch --opensearch-endpoint https://search.example --opensearch-index fieldora-search serve
fieldora-server --data-root D:\FieldoraData --job-backend postgresql --postgres-jobs-dsn-file D:\FieldoraSecrets\jobs.dsn run-job-worker --worker-id worker-a
fieldora-server --data-root D:\FieldoraData --media-metadata-backend postgresql --postgres-media-dsn-file D:\FieldoraSecrets\media.dsn serve
fieldora-server --data-root D:\FieldoraData --export-metadata-backend postgresql --postgres-exports-dsn-file D:\FieldoraSecrets\exports.dsn serve
fieldora-server --data-root D:\FieldoraData --science-backend postgresql --postgres-science-dsn-file D:\FieldoraSecrets\science.dsn serve
fieldora-server --data-root D:\FieldoraData --access-backend postgresql --postgres-access-dsn-file D:\FieldoraSecrets\access.dsn serve
```

The default listener is `127.0.0.1:8765`. Fieldora 0.08.23 refuses a non-loopback
listener unless `--tls-certificate` and `--tls-private-key` are supplied. Direct HTTPS
requires TLS 1.2 or newer and sends HSTS. `--allow-insecure-http` is an explicit
exception only for a trusted TLS-terminating reverse proxy; it is not suitable for a
direct network listener.

## Security properties

- default-deny PBAC remains authoritative;
- authorization is performed server-side per disclosed object;
- bearer tokens are returned once and stored only as hashes server-side;
- service API keys are one-time-disclosed, hashed, expiring, and revocable;
- device keys are bound to device identities and project-scoped role assignments;
- interactive device codes expire after ten minutes and are single-use after approval;
- OIDC tokens require pinned issuer/audience trust, HTTPS discovery or a local JWKS,
  verified claims, bounded key refresh, and explicit local identity mapping;
- decision audit uses a canonical predecessor hash chain and separately authorized,
  organization-filtered reads;
- search candidates are PBAC-filtered before result metadata or snippets are disclosed;
- renewable, fenced job leases recover abandoned work and reject stale completion,
  while job output requires independent authorization;
- project exports have distinct submit, status, and download PBAC gates, expire, and
  conceal their contained payload path;
- export revocation is separately authorized and expired or revoked payloads are
  physically removed while lifecycle metadata remains auditable;
- logout revokes the active token;
- API responses disable caching and add CSP, frame, and content-type protections;
- malformed and oversized login requests fail closed;
- authentication errors do not reveal whether a username exists.
- repeated login attempts are rate limited;
- authorized mutations use an immediate transaction and optional optimistic revision.
- media responses support resume, publish integrity metadata, and conceal denied IDs.
- uploads enforce ownership, contiguous offsets, size bounds, integrity, and atomic
  publication.

## Deliberate limits and next adapters

This release does not claim MFA, CSRF-resistant cookie sessions,
institutional signing-key recovery, multi-recipient encryption and managed key
recovery, electronic contract signing, or advanced faceted/geospatial search. Local PBKDF2
credentials are a bootstrap provider behind an authentication boundary. Remaining
PostgreSQL repositories will be introduced without weakening the
PBAC enforcement contract.

Phase F adds a declarative high-availability reference topology, PostgreSQL-backed
tenant quotas and request limiting, shared S3-compatible media and export objects,
continuous fenced workers, external-secret rotation metadata, and operational
governance. These are implementation-ready but production certification remains
conditional until the required node, service, recovery, upgrade, certificate, and
zone-failure exercises pass in one real multi-server environment. The in-process login
limiter remains a bootstrap-only control; production identity providers and ingress
must also enforce distributed authentication throttling.
