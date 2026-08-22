# Fieldora Product and Platform Roadmap

**Status:** Directional architecture roadmap  
**Baseline:** Fieldora 0.08.34  
**Planning method:** Capability gates rather than calendar promises

## 1. Product direction

Fieldora begins as a useful, offline-first personal nature evidence and research
application. It may grow into a collaborative scientific platform, but the server must
not become a prerequisite for owning, viewing, or exporting a personal library.

The roadmap preserves the existing principles:

- the user or institution owns its authoritative data;
- original media and provenance are evidence and are never silently rewritten;
- AI suggestions remain reviewable;
- Science is optional and independently stored;
- external contribution is deliberate, scoped, and reversible;
- local work remains possible without a network connection;
- migrations, compatibility, backup, and rollback are product features;
- domain boundaries and stable public identifiers precede distributed deployment.

Fieldora therefore develops as two compatible products over shared domain contracts:

1. **Fieldora Desktop** — a personal or field workstation with local authoritative
   storage, offline models, maps, taxonomy, and selected project data packs.
2. **Fieldora Platform** — one or more server installations for organizations,
   projects, contracts, shared evidence, policy enforcement, search, and web clients.

Desktop-to-platform exchange uses explicit synchronization and signed data packages.
It does not expose a desktop database as a shared network database.

## 2. Current baseline and gaps

Fieldora 0.08.34 currently provides a broad desktop foundation and governed one-node
server slice:

- local photo, sound, video, and document libraries;
- import, provenance, observations, taxonomy, maps, AI model management, export,
  reporting, jobs, maintenance, backup foundations, and diagnostics;
- optional Science navigation for projects, dossiers, artifact records, activities,
  budgets, resources, calendar work, and a vector/sticky whiteboard;
- a dedicated `science.sqlite3` database, stable cross-subsystem asset IDs, WAL,
  foreign keys, and bounded lock waiting;
- independently visible Library and Science workspaces.

The baseline is not yet ready for collaborative or very large installations:

- the incremental Science repository and shared application session await Windows
  field validation under realistic project workloads;
- the quarantined pre-0.05 Qt persistence adapter still awaits source cleanup after
  the comparison cycle;
- identity, PBAC, contracts, sessions, OIDC verification, device authorization, audit,
  server API, and a limited web client now exist, but production federation,
  administration, tenant operations, and universal enforcement remain incomplete;
- no desktop synchronization protocol, outbox/inbox, tombstone, or conflict model
  exists yet;
- SQLite and workstation filesystems are appropriate for local libraries, not for a
  shared catalog containing one billion assets;
- project data packs, leases, revocation, and selective offline disclosure are not yet
  implemented.

These gaps are release gates. Server work must not bypass them.

## 3. Target architecture

### 3.1 Shared logical domains

All editions use versioned contracts for:

- identity and organizations;
- users, service identities, groups, roles, permissions, and policies;
- projects, stages, activities, resources, budgets, dossiers, and artifacts;
- assets, renditions, checksums, provenance, observations, and taxonomy references;
- contracts, data classifications, grants, restrictions, embargoes, and consent;
- synchronization cursors, revisions, tombstones, conflicts, and audit events;
- data-pack manifests, signatures, encryption metadata, and expiry.

Desktop and server implementations may use different persistence technologies, but
public IDs, event semantics, package formats, and validation rules remain compatible.

### 3.2 Desktop deployment

Desktop remains a modular monolith:

- SQLite databases for bounded local authoritative data;
- filesystem or user-selected storage for originals;
- local search indexes and derived thumbnails;
- optional local AI, taxonomy, and map packages;
- an outbox/inbox synchronization adapter;
- encrypted, project-scoped offline data packs.

SQLite is retained for desktop because it supports portability and ownership. Desktop
scale limits must be measured and published; the billion-asset target applies to the
distributed platform, not to one SQLite file.

### 3.3 Platform deployment

The server evolves into independently scalable services behind stable APIs:

- stateless API and policy-enforcement services;
- PostgreSQL-compatible transactional stores, partitioned by tenant/project and time
  where justified by measured access patterns;
- S3-compatible object storage for originals and renditions, with immutable object
  versions, checksums, lifecycle policies, and replication;
- OpenSearch-compatible distributed text/faceted search;
- a dedicated geospatial store/index using PostGIS-compatible capabilities;
- an event log and durable queue for indexing, AI, package generation, and replication;
- caches used only for reconstructable data;
- an identity provider using OpenID Connect and OAuth 2.1 conventions;
- observability, audit export, backup, disaster recovery, and capacity controls.

No service treats a search index, cache, thumbnail, or AI result as the sole
authoritative record.

### 3.4 Multi-server installation

Supported deployment profiles should be introduced in this order:

1. single-node development and small-institution appliance;
2. highly available application tier with managed/external data services;
3. multi-node self-hosted installation with redundant API, workers, database,
   object storage, search, and ingress;
4. geographically replicated read services and governed cross-installation exchange.

Deployment is declarative, versioned, upgrade-tested, and supports:

- containers and Kubernetes-compatible orchestration;
- externally managed or bundled open-source dependencies;
- TLS, secret rotation, health/readiness probes, rolling upgrades, and rollback;
- restore drills and recovery-point/recovery-time objectives;
- node and service identity distinct from human accounts;
- placement constraints for data residency and contract obligations.

## 4. Identity, authorization, and contract rights

### 4.1 Identity and user management

The identity model includes:

- organizations and organization memberships;
- human users, invited guests, service accounts, devices, and API clients;
- local emergency administration plus federated OpenID Connect;
- optional MFA, session management, passwordless/federated login, account suspension,
  invitation expiry, and identity lifecycle events;
- groups and project teams;
- device registration and remote revocation for synchronized clients.

Authentication proves identity. It never determines access by itself.

### 4.2 Authorization model

Fieldora uses **policy-based access control (PBAC)** as the overarching
authorization model. PBAC evaluates versioned policies through a central policy
decision point and combines:

- **RBAC** for understandable roles such as platform administrator, organization
  administrator, project manager, researcher, contributor, reviewer, and viewer;
- **ABAC** for data attributes such as tenant, project, contract, classification,
  geography, species sensitivity, consent, embargo date, purpose, and device state;
- object-level grants for exceptional sharing;
- field-level and rendition-level disclosure when a user may see metadata or a
  redacted/low-resolution derivative but not the original.

Every API, search result, export, thumbnail, AI job, background worker, and data-pack
builder enforces the same policy decision. Hiding a button in a client is never a
security control.

RBAC, ABAC, contract rules, and object-level grants are inputs to PBAC; none is a
separate bypass around the policy decision and enforcement points.

Default policy is deny. Permission changes are versioned and audited. Administrators
can explain why access was allowed or denied without exposing unrelated protected data.

### 4.3 Contracts and data-use rights

A contract is a first-class, versioned domain object, not a text note attached to a
project. It may define:

- participating legal entities and responsible contacts;
- effective and expiry dates;
- projects, collections, assets, metadata fields, regions, taxa, and time ranges in
  scope;
- permitted purposes and operations: view, annotate, download, export, train AI,
  publish, sublicense, or administer;
- original, derivative, metadata-only, and aggregate-only access;
- sensitive-location redaction, embargoes, retention, deletion, and geographic
  residency obligations;
- download quotas, watermarking, attribution, license, consent, and review conditions;
- revocation behavior and handling of already downloaded offline data.

Contracts compile into policy grants but retain their legal identity and signed
versions. A new contract version never silently broadens an existing user's rights.
Contract expiry or revocation blocks new access immediately and marks offline packs for
revocation at their next check-in; expiry and residual-copy obligations remain visible
to administrators.

## 5. Billion-asset readiness

“Ready for one billion assets” means a tested system capacity, not a schema claim.
Readiness requires:

- globally unique, non-sequential public IDs and stable checksums;
- metadata separated from immutable media objects and derived renditions;
- tenant/project-aware partitioning without a single global hot table or sequence;
- cursor-based pagination and bounded queries; no unbounded counts or UI table loads;
- asynchronous ingest with idempotency keys, durable jobs, retry, quarantine, and
  backpressure;
- bulk metadata and manifest APIs rather than one request per asset;
- independently scalable indexing, thumbnailing, AI, package generation, and export;
- tiered object storage, lifecycle rules, deduplication policy, and integrity scrubbing;
- incremental search indexing with replay and full rebuild capability;
- partition-aware backup and restore, disaster recovery, and legal hold;
- per-tenant quotas, rate limits, cost attribution, and noisy-neighbor protection;
- privacy-safe metrics and tracing across asynchronous work;
- benchmark datasets and repeatable tests at 1 million, 10 million, 100 million, and
  1 billion metadata records, with representative object counts and query mixes.

The capacity gate is passed only when published service-level objectives are met for
ingest, common searches, project views, authorization filtering, export, recovery, and
reindexing under failure conditions.

## 6. Desktop integration and predefined project data sets

### 6.1 Server integration management

Desktop Settings gains an Integration Manager for:

- registering one or more Fieldora Platform endpoints;
- browser-based sign-in and device registration;
- selecting organizations and projects;
- viewing effective rights, quotas, contract scope, and expiry;
- choosing synchronization direction and schedules;
- monitoring outbox, inbox, conflicts, rejected records, storage, and last successful
  checkpoint;
- revoking a local endpoint or wiping its downloaded protected data without affecting
  the user's unrelated personal library.

Personal records stay local until a user deliberately assigns or contributes them to a
server project. Upload previews show fields and media that will leave the device.

### 6.2 Project data packs

Project managers define versioned data-pack profiles containing only what field users
need:

- selected projects, dossiers, activities, forms, protocols, and whiteboard templates;
- geographic/taxonomic subsets and sensitive-field redaction rules;
- map regions, taxonomy snapshots, reference media, and optional AI model packages;
- selected asset originals or bounded renditions;
- maximum size, expiry, refresh policy, and offline grace period.

The server resolves a profile against the requesting user's current contract and
authorization rights, then creates a signed manifest. Packs are encrypted per device or
user, checksum-verified, resumable, delta-updatable, and importable by cable or storage
media when network transfer is unavailable.

Desktop keeps downloaded project data in a separate managed cache/store, not mixed
irreversibly into the personal authoritative library. Users can see pack provenance,
version, storage use, expiry, and pending revocation. Locally created records retain
provenance and synchronize through an outbox when permitted.

## 7. Delivery roadmap

### Phase A — 0.05: Science integrity and architecture recovery

**Status:** Internal validation passed. Subsystem registration, health/integrity,
verified backup/restore payloads, global revision conflict detection, repository
contracts, one shared application session, incremental record writes, dossier
lifecycle basics, and whiteboard position persistence are built. Removal of the
quarantined pre-0.05 Qt adapter follows field validation; it is no longer executed.

**Outcome:** the current desktop feature set becomes production-safe enough to extend.

- Extract Science domain contracts, application commands, repository interfaces, and
  SQLite migrations from Qt.
- Replace full-table rewrites with incremental, revision-checked mutations.
- Register Science in backup, restore, health, diagnostics, and storage inventory.
- Complete dossier edit/search/delete, artifact relations, broken-media diagnostics,
  revisions, provenance, and whiteboard geometry updates.
- Define stable IDs and revision envelopes for every synchronizable entity.
- Establish architecture boundary and migration contract tests.

**Exit gate:** Qt contains no SQL; crash/recovery, migration, backup/restore, and
concurrent-edit tests pass; no known authoritative Science data-loss path remains.

### Phase B — 0.06: Portable projects and offline packages

**Status:** Portable project foundation built. Checksum-verified project export,
explicit Library-reference redaction, import preview, collision policies, atomic
repository import, and safe project removal are internally validated. Cryptographic
signatures, originals/renditions, predefined map/taxonomy/AI sets, encryption, and
governed server packs remain later work.

**Outcome:** projects can move safely between standalone installations before a server
is required.

- Versioned project/dossier export package with explicit media inclusion.
- Signed manifest, checksums, schema version, provenance, license, and redaction report.
- Import preview, collision handling, dry run, rollback, and compatibility validation.
- Data-pack storage boundary and package manager in Desktop.
- Predefined local sets for maps, taxonomy, reference media, AI resources, and forms.

**Exit gate:** a disconnected machine can import, use, update, and remove a project
pack without corrupting or exposing the personal library.

### Phase C — 0.07: Identity and policy foundation

**Status:** Local foundation built. Identity types, organization boundaries, scoped
roles, contracts, PBAC policy sources, default-deny decisions, explicit-deny
precedence, field/purpose/attribute constraints, fail-closed enforcement contracts,
decision audit, isolated persistence, and local administration are internally
validated. Authentication, federation, sessions, cryptographic audit integrity, and
server-wide enforcement remain Phase D work.

**Outcome:** authorization semantics exist independently of any web UI.

- Organization, user, group, role, permission, service account, device, and session
  domains.
- PBAC foundation with RBAC, ABAC, contract policy, and object-level grant inputs,
  all using default deny.
- Contract, classification, embargo, consent, purpose, retention, and data-grant model.
- Central policy-decision contract and enforcement adapters.
- Append-only security audit events with integrity protection and export.
- Field/rendition-level authorization tests and explainable decisions.

**Exit gate:** every command/query/export can be evaluated against the same policy test
suite; cross-tenant and expired-contract tests prove denial.

### Phase D — 0.08: Server API and first web client

**Status:** Implementation complete; exit conditionally blocked. Local password bootstrap, opaque expiring sessions,
the versioned `/api/v1` boundary, per-record PBAC filtering, session revocation, and a
limited responsive project/dossier web client are validated. PBAC-authorized project
and dossier writes now include revision-conflict protection, and login attempts are
bounded. Governed media registration and PBAC-filtered byte-range delivery conceal
storage paths and denied object identities. Persistent, owner-bound upload sessions
now verify contiguous chunks, declared size, and SHA-256 before atomic publication.
Scoped service credentials are one-time-disclosed, hashed, expiring, revocable, and
remain subject to PBAC. Administrator-enrolled device credentials bind standalone and
field clients to explicit device identities and project-scoped roles, while a
short-lived interactive device flow adds PBAC approval and one-time exchange. OIDC
verification now supports either a pinned local JWKS or HTTPS discovery with exact
issuer validation, bounded signing-key caching, and one refresh for routine rotation.
Signed external subjects map to local users without importing external claims as
permissions. Production operations and advanced
search, and
production deployment automation remain open. The 0.08.34 evidence audit confirms the
automated policy boundary but blocks formal exit until live PostgreSQL, S3/OpenSearch,
and installed-client TLS certification has reviewable evidence.

PBAC decision events are now transactionally hash-chained, verifiable, and exposed
only through a separately authorized, organization-filtered audit API.

The complete access-control repository now has a PostgreSQL adapter covering identity,
credentials, sessions, federation, roles, PBAC, contracts, approvals, and audit.
Concurrent audit writers serialize sequence/hash creation with a transaction advisory
lock. Together with the Science, jobs, media, and export adapters, the planned
PostgreSQL repository parity set is complete.

The isolated search projection is deterministically rebuildable and filters every
candidate through PBAC before returning result metadata or snippets.

Server deployments can now select an HTTPS OpenSearch-compatible projection. Rebuilds
use a fresh concrete index and atomic alias switch, requests and responses are bounded,
and bearer credentials come from a separate token file. The external index remains
reconstructable and every candidate still passes PBAC before disclosure.

Shared Science records now have a PostgreSQL adapter with JSONB payloads, per-record
revisions, and snapshot-wide optimistic transactions. API operations, indexing, and
portable-project workers use the same selected source; standalone Science remains an
independent SQLite database.

Durable leased server jobs now survive worker interruption, and their status/output
requires authorization independently from submission.

Independent job-worker processes now claim work with explicit worker identity,
renewable leases, and unique fencing tokens. Superseded workers cannot commit stale
results. The reference SQLite queue supports these processes on one server; the same
claim contract now has a PostgreSQL adapter using atomic skip-locked claims for
cross-node operation.

Portable project exports now run as durable jobs. Submission, job visibility, and
download are three independent PBAC gates. Completed packages live beneath a contained
server root, have SHA-256 and expiry metadata, support byte ranges, and never disclose
their storage path. Original Library media remains excluded. Object-storage lifecycle
remains Phase D/E work. A distinct
PBAC action can now revoke an export immediately, removing its payload while retaining
audit metadata; a deterministic maintenance command purges expired payloads.

Export lifecycle and attestation metadata now have a PostgreSQL adapter. Conditional
revocation and signing updates prevent competing writers, while bounded skip-locked
expiry claims coordinate independent maintenance workers.

Time-bounded project contracts can now create narrowly mapped PBAC grants for project
view/search, upload, export submission, job visibility, and export download. Contract
dates are normalized to UTC, project scope is mandatory, cross-organization subjects
are rejected, and suspension or termination takes effect at the next decision. A
remotely governed administration API and electronic-signature workflow remain open.

An explicitly initialized Ed25519 server identity can now issue detached attestations
over the SHA-256 of complete export archives. Attestations are stored with the governed
export, protected by the same download PBAC decision, and verifiable offline against a
separately distributed trust file. The strict portable ZIP format remains unchanged;
automatic key generation, institutional trust exchange, rotation, revocation lists,
and managed private-key recovery remain open.

Exports can now be encrypted for a named X25519 recipient public key using a fresh
ephemeral key, HKDF-SHA256, and streaming AES-256-GCM. Only public recipient material
enters the durable server job. The recipient verifies the optional Ed25519 attestation
over the delivered ciphertext and decrypts locally with a private key that never
reaches the server. Multi-recipient envelopes, managed key recovery, rotation,
revocation lists, and Desktop pack-manager integration remain open.

The authenticated server API can now create, list, inspect, and change project
contract status. Every operation is protected by `administer_contracts` PBAC at the
target organization/project, list disclosure is cursor-bounded and per-record filtered,
and denied object identities remain concealed. Remote suspension or termination
invalidates derived grants at the next decision.

The limited responsive web client now includes a separate Contracts workspace for
bounded listing, grant creation, explicit right selection, and lifecycle changes. It
uses accessible tabs and labelled controls, session-only bearer storage, safe text
rendering, and explicit administration purpose. Server PBAC remains authoritative.
Delegated workflows, bulk administration, and a broader platform operations console
remain open.

Contract creation can now be marked for independent approval. A proposal has no
derived allow policies; `approve_contracts` is distinct from administration; the
requester cannot self-approve; and activation plus all policies commit atomically.
Approver identity/time are retained in contract terms, and direct or reactivation
bypasses are blocked. A bounded one-to-ten quorum now records distinct organizational
approvers while keeping the contract non-authorizing until the final approval.
Electronic signatures remain open. A distinct cursor-bounded approval
queue now lets delegated approvers discover only proposals authorized by
`approve_contracts` PBAC, without granting contract-administration rights. A bounded
expiry queue now lets authorized administrators review active contracts ending inside
a configurable window without disclosing contracts outside their PBAC scope.

Governed media now uses a replaceable object-store boundary. The contained filesystem
adapter remains the standalone default, while an optional S3-compatible adapter
supports opaque-key publication and exact range reads without exposing direct object
URLs or credentials. Broader export-object lifecycle and production provider
certification remain open.

Governed-media records and resumable-upload state now have a PostgreSQL adapter with
64-bit sizes, constrained hashes, optimistic offsets, and atomic completion. Object
bytes remain independently selectable through the filesystem/S3 boundary.

The one-node listener now supports direct TLS 1.2+ with HSTS and refuses non-loopback
HTTP unless an operator explicitly declares a trusted TLS terminator.

One-node recovery bundles now take online-consistent SQLite snapshots, include local
governed objects, verify an exact hash manifest and database integrity, and restore
only to a new data root. Provider-managed S3 objects and private trust material remain
explicit external dependencies. The recovery copy can now be opened through every
current server adapter, migrated, integrity-checked, composed offline, and certified
through an atomic readiness report before deployment.

OIDC discovery now validates the provider's exact issuer, requires HTTPS metadata and
JWKS endpoints, bounds metadata downloads and refresh intervals, and retries one key
refresh for an unknown signing-key ID. Local identity mapping and PBAC remain the only
source of Fieldora authority.

**Phase transition:** the deployment team reported the provider-backed certification
executed and explicitly authorized Phase E development. The reviewable evidence must
still be attached before a formal Phase D audit artifact is changed from conditional;
Phase E release certification cannot use this operator confirmation as a substitute.

**Outcome:** a small institution can operate one governed Fieldora server.

- Versioned HTTP API, OpenID Connect integration, device authorization, and scoped
  service credentials.
- PostgreSQL-compatible repository, S3-compatible object adapter, durable jobs, and
  search projection.
- Responsive web client with limited viewer, contributor, reviewer, and project-manager
  experiences.
- Authorized upload, resumable download, project/dossier workflows, review, audit, and
  administration.
- One-node reference deployment and automated upgrade/restore tests.

**Exit gate:** no web client can obtain data through direct object URLs, search, export,
or job output beyond the API policy decision.

### Phase E — 0.09: Desktop synchronization and governed data packs

**Outcome:** standalone and field clients participate without surrendering offline use.

**Completed in 0.09.6:** the desktop owns validated HTTPS endpoint accounts,
durable device registrations, revision-guarded project enrollments, and a default-deny
effective-rights projection. Restart-safe push/pull journals add idempotency, cursors,
tombstones, retry leases, and conflict records. A versioned transport coordinator now
maps remote outcomes into those journals with rights gating and page-atomic cursor
advancement. Authenticated `/api/v1` binding and restart-safe ranged media transfer
now complete the transport foundation. Contribution preview, current-terms
acknowledgment, and explicit conflict resolution complete the user-review boundary.
Policy-filtered full and delta project packs install into an isolated governed cache
with checksum and exact-base validation. AES-256-GCM encryption, Ed25519 signatures,
expiry enforcement, revocation state, content-key destruction, and encrypted-envelope
removal complete the governed-pack lifecycle. `PHASE_E_EXIT_GATE.json` records the
passing deterministic exit evidence.

- Endpoint/account manager, device registration, project enrollment, and rights view.
- Revision-based pull/push protocol, durable outbox/inbox, tombstones, idempotency,
  retry, conflict presentation, and resumable media transfer.
- Server-generated, policy-filtered project data packs with delta updates.
- Pack encryption, signature verification, expiry, revocation state, and secure removal.
- Explicit contribution preview and contract/license acknowledgment.

**Exit gate:** interrupted synchronization resumes deterministically; revoked or expired
rights prevent new disclosure; offline-created data preserves full provenance.

### Phase F — 0.10: Multi-server production deployment

**Outcome:** high availability and operational governance.

- Redundant APIs and workers, database failover, replicated object storage, distributed
  search, ingress, TLS, secret rotation, and declarative deployment.
- Tenant administration, quotas, rate limits, usage/cost reporting, retention jobs,
  legal holds, and audit export.
- Rolling upgrades, rollback, backup, point-in-time recovery, disaster recovery, and
  restore drills.
- Security threat model, dependency/SBOM controls, penetration testing, incident
  response, and administrator runbooks.

**Exit gate:** availability, security, recovery, and upgrade objectives pass under node,
service, and zone failure exercises.

### Phase G — 0.11–0.12: Large-catalog scaling

**Outcome:** architecture and operations are proven progressively.

- Partition and routing strategy based on measured query/ingest behavior.
- Bulk ingest, backpressure, tiered storage, projection rebuild, and lifecycle services.
- Scale tests and operational validation at 1M, 10M, and 100M assets.
- Cross-installation governed exchange without creating a universal unrestricted
  catalog.
- Read replicas and regional delivery for authorized renditions and metadata.

**Exit gate:** 100-million-asset tests meet published service objectives with failure,
reindex, backup, restore, and authorization filtering included.

### Phase H — 1.0 Platform: one-billion-asset certification

**Outcome:** a supported, evidence-based billion-asset platform release.

- One-billion-record metadata/search benchmark with representative tenants, projects,
  rights, contracts, media objects, and spatial/taxonomic distributions.
- Sustained ingest, concurrent search, policy filtering, pack building, and audit load.
- Proven full projection rebuild, partition recovery, disaster recovery, and regional
  failover.
- Capacity calculator, reference topologies, cost/storage model, and published limits.
- Upgrade path from all supported Desktop and Platform releases.

**Exit gate:** independent release review confirms correctness, isolation, recovery,
security, and agreed service levels at target scale. “One billion” is not used as a
production claim before this gate.

## 8. Cross-cutting work in every phase

- accessibility for desktop and web clients;
- threat modeling, privacy review, and dependency/license review;
- immutable evidence provenance and AI decision traceability;
- migration, downgrade/rollback strategy, and compatibility fixtures;
- performance budgets and telemetry that do not expose protected research;
- documentation for users, administrators, developers, auditors, and data stewards;
- clear feature status: Proposed, Approved, Implementation Prepared, Build Completed,
  Internal Validation Passed, Awaiting Field Validation, Field Validated, Corrective
  Build, or Frozen.

## 9. Deliberate non-goals

- A central server does not gain unrestricted access to personal Desktop libraries.
- A web client is not trusted to enforce permissions by hiding interface elements.
- Search indexes and AI outputs are not authoritative evidence stores.
- Contract rights are not represented only as roles.
- Desktop SQLite databases are not mounted on a network share for collaboration.
- A billion-asset target does not justify unbounded queries, premature microservices,
  or removal of offline ownership.
- Offline packs cannot guarantee erasure from an uncontrolled or compromised device;
  contracts, short-lived keys, minimized disclosure, expiry, watermarking, audit, and
  operational controls reduce and document that risk.

## 10. Immediate approved planning backlog

Before implementation of server features, produce and approve:

1. Science extraction ADR and incremental migration plan.
2. Identity, tenancy, role, policy, contract, and audit domain specification.
3. Data classification and sensitive-species/location threat model.
4. Synchronization protocol and conflict-resolution specification.
5. Project data-pack format, encryption, expiry, and revocation specification.
6. Server storage/search technology ADR with portability requirements.
7. Billion-asset workload model, service-level objectives, and benchmark plan.
8. Multi-server deployment, backup, disaster-recovery, and upgrade architecture.
9. Licensing/SBOM policy for bundled open-source services and web components.
10. Field-validation plan covering low bandwidth, offline work, removable-media
    transfer, revocation, and accidental data disclosure.

This sequence keeps the roadmap aligned with Fieldora’s central promise: personal
curiosity and scientific collaboration can grow together without sacrificing
ownership, evidence integrity, or deliberate control over sharing.
**Completed in 0.09.7:** the custom Science canvas is replaced by an offline
Excalidraw-compatible Documents workflow. Whiteboard version snapshots are
owned by Documents, new dossier relations use Document links, and existing
Science whiteboard rows are intentionally not migrated.
