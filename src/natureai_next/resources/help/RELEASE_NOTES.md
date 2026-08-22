## Fieldora 0.11.14 — thumbnail recovery repair

- Fixes thumbnail jobs failing when transient job states were written into the
  derivative-cache state column.
- Requeues the same completed derivative job when its disposable cache file or
  valid catalog record has disappeared.
- Recovers existing failed thumbnail backlogs through the delayed background
  reconciliation without blocking startup or gallery navigation.
- Preserves valid thumbnails when a later rebuild attempt fails.

## Fieldora 0.11.13 — offline OpenSeaMap overlays

- Adds verified import of prepared OpenSeaMap raster MBTiles seamark overlays.
- Composes enabled nautical layers over both raster and vector offline basemaps.
- Keeps import and copying in Activity Center so map management remains usable.
- Records checksum, bounds, zoom range, source, attribution, licence and
  reference-only navigation status.
- Never bulk-downloads public OpenSeaMap tiles and displays a persistent warning
  that the layer is not a certified navigational chart.

## Fieldora 0.11.12 — governed deletion approvals

- Restores a clearly named Trash & Deletion Approvals workspace.
- Routes organizational deletion to a named person or organization function.
- Falls back deterministically to another administrator, a sole administrator,
  or the Fieldora tool administrator when no requested approver exists.
- Prevents requester self-approval when an independent assigned approver exists.
- Adds pending approval, rejection and approved deletion handling with audit
  history and backup coverage.

## Fieldora 0.11.11 — recognizable native process names

- Produces separate native Windows executables for Fieldora desktop,
  maintenance, manuals, server, workers, updater and recovery.
- Embeds Fieldora product, description, original filename and release metadata
  for Task Manager and Windows file properties.
- Uses frozen PyInstaller applications rather than renaming `python.exe` or
  `pythonw.exe`.
- Retains source-based debug and compatibility entry points.

## Fieldora 0.11.10 — non-blocking thumbnail pipeline

- Makes gallery thumbnail workers cache readers only; original decoding and
  cache writes remain in the durable background job engine.
- Stops thumbnail polling immediately when the user leaves the Photos screen
  and resumes lightweight cache checks when the screen is activated again.
- Adds visible checking, queued and awaiting-generation status while preserving
  placeholder-driven navigation.
- Delays large missing-thumbnail reconciliation until after the desktop is
  interactive, keeping startup and screen changes within the three-second
  response budget.

## Fieldora 0.11.9 — maritime research logs and depth

- Moves Maritime Operations from Platform Operations into the Research group
  beside Projects & Tasks.
- Adds a dedicated Submarine Logs screen alongside Dives and Operation Logs.
- Adds depth in metres as a first-class registration, table and export field.
- Adds a first-class Buddy / dive partner field to Dive Log registration,
  display and export.
- Safely extends existing marine-maritime databases without discarding records.

## Fieldora 0.11.8 — Home navigation startup hotfix

- Places the Home leaf inside the navigation tree's required Overview branch.
- Prevents the desktop tree builder from treating the route string as branch
  children and raising a tuple-unpacking `ValueError` during startup.
- Adds a structural regression guard for every root-level navigation branch.

## Fieldora 0.11.7 — home dashboard and calendar visibility

- Adds a purpose-built Home screen with research, evidence and upcoming-work
  summaries plus direct workspace actions.
- Highlights scheduled days in Research Calendar and Projects & Tasks, with a
  visible activity-count badge on each date.
- Adds standards-based iCalendar export and deliberate one-click event creation
  in Google Calendar and Outlook.
- Keeps background provider synchronization disabled until an administrator
  configures a separately governed OAuth integration.

## Fieldora 0.11.6 — marine science and maritime operations

- Adds independently switchable Marine & Freshwater Science and Maritime
  Operations modules.
- Adds dedicated screens for stations, surveys, samples, measurements, species
  and eDNA evidence, habitats, acoustic/sonar records, vessels, voyages, ports,
  routes, crew, equipment, dives and operation logs.
- Stores the domains in a dedicated WAL-backed subsystem with attachment links
  and immutable audit history.
- Exports a portable `fieldora.marine-maritime.v1` JSON contract while retaining
  existing access-contract authority over linked Library assets.

## Fieldora 0.10.16 — assigned review, multi-enrichment, OCR, and PDF navigation

- Adds durable, audited review assignments for legacy photo suggestions and
  canonical sound, video, and document enrichment. Reviewers can defer an item
  to a user identity, filter that user's queue, or return it to the shared queue.
- Removes media-specific AI Review tabs when the corresponding Library type is
  disabled, while retaining its data and historical decisions.
- Adds multi-enrichment selection to the capability execution screen. Each
  selected capability runs independently, keeps its own progress screen, and
  persists producer-neutral results.
- Adds installable offline document OCR based on PyMuPDF and RapidOCR ONNX.
  Embedded PDF text is preserved; scanned pages produce page-specific text and
  normalized review regions without requiring a separate Tesseract installation.
- Enables continuous multi-page PDF viewing, fit-to-width scrolling, and a
  working page rail.

## Fieldora 0.10.15 — parallel multi-library analysis

- Extends multi-file capability execution to Photos, Sounds, Videos, and
  Documents for every compatible installed or server-backed analysis.
- Runs up to four selected files concurrently through a bounded worker pool,
  with cooperative cancellation and per-file failure isolation.
- Adds an independent batch-analysis screen to each media library with live
  queued, running, succeeded, failed, and cancelled states.
- Connects each analysis screen to its Library Types switch: disabling the
  parent library hides the screen and cancels remaining work without deleting
  completed or historical results.
- Retains producer-neutral capability parameters and canonical enrichment
  persistence for every file.

## Fieldora 0.10.14 — Excalidraw React initialization fix

- Removes the React render loop that prevented the bundled Excalidraw toolbar
  and canvas from initializing.
- Keeps the document bridge and delayed save callback stable across editor
  renders by storing them in non-rendering references.
- Preserves the 500 ms automatic-save debounce without storing its timer in
  React state.
- Moves the packaged-file content-security policy into the maintained web
  source so rebuilding Excalidraw cannot silently remove the offline asset
  permissions.

## Fieldora 0.10.13 — full Excalidraw runtime loading fix

- Permits the bundled local Excalidraw JavaScript, styles, fonts, workers, and
  WebAssembly under the network-blocked content-security policy.
- Keeps all remote connections blocked while allowing only packaged `file:`,
  Qt bridge, data, and blob resources.
- Detects a loaded page that failed to create the Excalidraw toolbar and canvas.
- Replaces unexplained white panes with a visible Qt WebEngine or JavaScript
  diagnostic suitable for installation repair.

## Fieldora 0.10.12 — standalone offline Manuals application

- Adds a separate Fieldora Manuals desktop application using the same offline,
  searchable browser pattern as integrated Help.
- Bundles extensive Installation, Administrator, and User manuals inside the
  application package.
- Adds cross-manual full-text search and role-labeled manual navigation.
- Adds a Fieldora Manuals command to the Help menu and an independent
  `fieldora-manuals` GUI launcher.
- Requires no network connection and opens alongside Fieldora without blocking
  the main window.

## Fieldora 0.10.11 — Excalidraw startup hotfix

- Fixes a startup-blocking `NameError` when the Science whiteboard workspace
  populates its embedded Excalidraw document list.
- Imports the Qt `QListWidgetItem` type used by the list refresh path.
- Adds a source-level regression check so the constructor dependency cannot be
  removed unnoticed.
- The Qt WebEngine profile warning seen after the crash was teardown fallout; the
  primary constructor failure is removed.

## Fieldora 0.10.10 — Phase F live-certification workflow

- Adds a machine-readable certification plan covering all nine required failure,
  recovery, certificate, upgrade, and zone exercises.
- Defines the objective, required observations, and provider-artifact guidance for
  every exercise without pre-populating or implying a result.
- Adds a fail-closed status command that validates evidence digests and accepts only
  passing records from one explicitly named environment.
- Returns a non-success status while evidence is missing, failed, or mixed across
  environments, keeping implementation readiness distinct from certification.
- Extends the Phase F gate, operator documentation, SBOM, and regression coverage.

## Fieldora 0.10.9 — Phase F verified audit-export administration

- Exports tenant-scoped security events directly from the authoritative SQLite or
  shared PostgreSQL access-control repository.
- Verifies the complete append-only hash chain before any export archive is written
  and fails closed on predecessor, count, or event-hash damage.
- Derives organization scope from each recorded authorization request and excludes
  other tenants before serialization.
- Adds bounded operator export and independent archive-verification commands.
- Extends the Phase F gate, operations documentation, SBOM, and regression coverage.

## Fieldora 0.10.8 — Phase F external-secret rotation administration

- Adds a shared PostgreSQL registry for coordinating externally managed secret
  versions across production replicas.
- Serializes activation per secret purpose and requires the operator's expected
  active version, preventing concurrent rotations from silently superseding one
  another.
- Accepts metadata references only for Vault, KMS, or external-secret providers;
  secret values never enter Fieldora's registry or command arguments.
- Adds operator commands to stage, activate, and inspect version history with
  standalone SQLite parity.
- Extends the Phase F gate, operations guidance, SBOM, and regression coverage.

## Fieldora 0.10.7 — Phase F retention and legal-hold administration

- Adds a shared PostgreSQL retention repository for multi-server maintenance workers.
- Claims due work with `FOR UPDATE SKIP LOCKED`, renewable time bounds, and incrementing
  fencing tokens.
- Excludes organization-wide, resource-type, and resource-specific legal holds inside
  the same claim transaction.
- Adds operator commands to register deadlines, place and release holds, claim bounded
  work, and complete deletion only with the current worker and fencing token.
- Retains standalone SQLite parity and extends documentation, Phase F evidence, and
  regression coverage.

## Fieldora 0.10.6 — Phase F tenant governance administration

- Adds a supported operator CLI for tenant quota configuration over standalone SQLite
  and shared PostgreSQL governance repositories.
- Preserves optimistic revisions so concurrent quota administrators cannot silently
  overwrite each other.
- Adds tenant-scoped usage reports over explicit time ranges.
- Adds deterministic decimal cost calculation from an operator-supplied metric price
  table without binary floating-point rounding.
- Validates bounded DSN and pricing files and extends the Phase F exit gate and
  regression coverage.

## Fieldora 0.10.5 — Phase F production recovery contract

- Adds a machine-verifiable backup, point-in-time recovery, and disaster-recovery
  contract with explicit five-minute RPO and one-hour RTO ceilings.
- Requires verified immutable PostgreSQL base backups, continuous WAL archiving,
  restore-to-new-target drills, encrypted recovery points, and integrity checks.
- Requires versioned cross-zone object replication, checksummed inventory, deletion
  state, and legal-hold preservation.
- Requires search rebuild from authoritative repositories with atomic alias switching
  and externally managed recovery-key custody.
- Adds an installed assessment CLI, reference plan, fail-closed tests, and Phase F
  exit-gate integration.

## Fieldora 0.10.4 — Phase F graceful rollout lifecycle

- Coordinates SIGTERM and SIGINT handling for API and worker processes.
- Marks API replicas unready before shutdown, preserves liveness during a bounded
  drain window, and then closes the HTTP server cleanly.
- Stops workers from claiming new jobs after shutdown is requested while allowing the
  currently fenced job to complete.
- Adds explicit API and worker termination grace periods to the Kubernetes reference.
- Makes shutdown callbacks idempotent and extends the Phase F gate and regression
  coverage for rolling-upgrade behavior.

## Fieldora 0.10.3 — Phase F production readiness

- Separates process liveness, startup, and dependency readiness endpoints.
- Removes an API replica from service when PostgreSQL, S3-compatible storage, or
  OpenSearch is unavailable without restarting an otherwise healthy process.
- Keeps liveness independent of external dependencies to avoid cascading restart
  loops during provider outages.
- Caches bounded readiness results and returns component booleans without exposing
  connection strings or exception details.
- Updates Kubernetes probes and Phase F gate evidence for the production semantics.

## Fieldora 0.10.2 — Phase F shared production runtime

- Moves governed export payloads behind the replaceable object-storage boundary, so
  exports produced by any worker can be downloaded or revoked through any API replica.
- Configures production workers with shared PostgreSQL metadata, S3-compatible
  objects, and OpenSearch instead of node-local fallbacks.
- Adds continuous bounded worker polling suitable for orchestrated deployments.
- Repairs the container runtime-root creation and excludes local data, caches,
  archives, and development dependencies from the build context.
- Extends the Phase F gate and regression coverage for the shared runtime boundary.

## Fieldora 0.10.1 — Phase F certification evidence hardening

- Adds an installed evidence-recorder CLI for all nine Phase F infrastructure
  exercises.
- Copies provider output into the evidence set and verifies its SHA-256 digest before
  accepting an exercise record.
- Rejects missing, tampered, duplicated, malformed, or unattributed exercise evidence.
- Requires one consistent certification environment before the Phase F gate can pass.
- Makes the container base image configurable so production builds can inject an
  independently verified digest instead of relying on an unverified hard-coded value.

## Fieldora 0.10.0 — Phase F deployment foundation

- Adds a machine-verifiable multi-server production topology contract.
- Requires redundant zonal APIs and fenced workers, PostgreSQL failover and PITR,
  replicated encrypted object storage, distributed search, TLS ingress, external
  secret rotation, and zero-unavailable rolling upgrades.
- Keeps production certification conditional until node, service, recovery, upgrade,
  certificate-rotation, and zone-failure exercises provide evidence.
- Ships a reference production declaration, assessment CLI, operator guidance, and
  fail-closed regression coverage.
- Adds durable tenant quotas and usage reporting, fenced retention claims, legal
  holds, integrity-addressed tenant audit exports, and external-secret rotation
  metadata.
- Adds the Phase F threat model, incident-response and administrator runbooks,
  deterministic dependency SBOM, exercise-evidence format, and conditional exit gate.

## Fieldora 0.09.10 — embedded Excalidraw opens immediately

- Creates `Drawing 1` automatically when the Whiteboards workspace is empty.
- Opens the first local whiteboard directly in Fieldora, so the embedded canvas is
  visible without selecting a file or installing Excalidraw separately.
- Identifies Excalidraw 0.18.1 in About, Licences & Attribution,
  Acknowledgements, and System Information.
- Retains local autosave, document version snapshots, network blocking, and the
  no-whiteboard-migration boundary.

## Fieldora 0.09.9 — full offline Excalidraw application

- Embeds the full Excalidraw 0.18.1 application directly in the Science workspace.
- Bundles all editor JavaScript, styles, fonts, locales, and diagram modules.
- Blocks network schemes in both the WebEngine profile and page security policy.
- Loads and atomically autosaves standard `.excalidraw` files through Documents.
- Keeps manual immutable document versions and preserves the no-whiteboard-migration
  boundary.

- Corrects the startup splash to the Fieldora identity and product description.
- Renames the bundled tree icon and new Windows/Linux launcher links to Fieldora.
- Labels the About link as the Fieldora project website and shows a link icon.
- Replaces the active custom Science canvas with offline Excalidraw-compatible
  documents stored and versioned through Documents.
- Leaves existing custom whiteboards untouched; no whiteboard migration is required.
- Accepts a checksum-valid older core schema, creates a verified backup, and applies
  only the known additive Phase E migrations before startup.
- Removes current Fieldora links and legacy Aperture/NatureAI links during uninstall
  on Windows, and removes both Fieldora and compatibility launchers on Linux.

# Build 35 — Platform Completion

## Fieldora 0.08.34 — Phase D exit-gate evidence audit

- Adds a machine-readable, fail-closed Phase D exit-gate checker and a reviewable
  evidence matrix.
- Confirms automated implementation evidence for PBAC-governed media, search,
  exports, job output, and one-node recovery.
- Records the formal gate as conditional instead of claiming completion: live
  PostgreSQL, S3/OpenSearch, and installed-client TLS certification remain blocked.
- Defines the exact provider-backed closure procedure required before Phase E starts.

## Fieldora 0.08.33 — PostgreSQL access-control parity

- Adds PostgreSQL parity for organizations, human/service/device identities,
  credentials, sessions, federation mappings, groups, roles, PBAC policies, contracts,
  approvals, and security audit.
- Reuses the complete tested access-control repository behavior over a PostgreSQL
  compatibility boundary rather than introducing a reduced authorization model.
- Serializes concurrent audit appends with a transaction-scoped advisory lock before
  sequence and predecessor-hash calculation.
- Adds independent access backend and bounded DSN-file configuration.
- Completes the planned PostgreSQL repository slices for access, Science, jobs, media,
  and exports while retaining SQLite defaults for standalone operation.

## Fieldora 0.08.32 — PostgreSQL Science repository

- Adds a PostgreSQL repository for shared Science projects, dossiers, activities,
  artifacts, project planning, and whiteboards.
- Preserves snapshot-wide optimistic concurrency and per-record revisions.
- Stores payloads as JSONB and applies multi-record snapshot changes atomically.
- Uses the same PostgreSQL Science source for API reads/writes, search rebuild jobs,
  and portable-project export jobs.
- Adds independent Science backend and bounded DSN-file configuration.
- Keeps the standalone `science.sqlite3` database unchanged; access-control PostgreSQL
  parity is the remaining repository slice.

## Fieldora 0.08.31 — PostgreSQL governed-export metadata

- Adds a PostgreSQL repository for governed project-export lifecycle metadata.
- Uses 64-bit sizes, timezone-aware lifecycle fields, digest constraints, and scoped
  indexes.
- Makes revocation and attestation attachment conditional single-writer operations.
- Claims bounded expiry batches with `FOR UPDATE SKIP LOCKED` before payload removal,
  preventing duplicate cleanup across maintenance workers.
- Adds independent export-metadata backend and bounded DSN-file configuration.
- Keeps SQLite as the standalone default; access-control and Science PostgreSQL parity
  remain follow-up work.

## Fieldora 0.08.30 — PostgreSQL governed-media metadata

- Adds a PostgreSQL repository for governed-media records and resumable-upload state.
- Keeps media bytes behind the existing contained filesystem or S3-compatible
  object-store contract.
- Uses 64-bit sizes, database constraints, scoped indexes, and optimistic offset
  updates.
- Locks the completed upload row and atomically inserts the media record plus removes
  upload state.
- Adds independent media-metadata backend and bounded DSN-file configuration.
- Keeps SQLite as the standalone default; access control, Science, and export metadata
  PostgreSQL parity remain follow-up work.

## Fieldora 0.08.29 — PostgreSQL distributed-job repository

- Adds the first PostgreSQL parity slice for the authoritative server job queue.
- Claims one job atomically with `FOR UPDATE SKIP LOCKED`, allowing independent
  cross-node workers without serializing idle claimers.
- Uses `JSONB` payload/result fields and timezone-aware lease timestamps.
- Preserves worker identity, renewable leases, bounded attempts, and fencing-token
  completion semantics from the SQLite reference adapter.
- Adds optional `server-postgresql` packaging and DSN-file configuration.
- Keeps SQLite as the default; access control, Science, media, and export registry
  PostgreSQL parity remain explicit follow-up work.

## Fieldora 0.08.28 — external OpenSearch projection

- Adds an optional HTTPS OpenSearch-compatible search projection while retaining
  SQLite FTS as the standalone default.
- Rebuilds into a new concrete index and atomically switches the configured alias.
- Bounds queries to ten normalized terms, 500 candidates, and 2 MiB responses.
- Accepts authentication through a bearer-token file so secrets do not enter command
  arguments.
- Rejects insecure endpoints, URL credentials, cross-origin redirects, invalid aliases,
  malformed documents, and bulk-index errors.
- Keeps search non-authoritative: the API evaluates every candidate through PBAC before
  disclosing title or snippet.

## Fieldora 0.08.27 — fenced independent job workers

- Adds explicit worker identities and unique lease fencing tokens to every server-job
  claim.
- Renews active leases in the background while a handler runs.
- Prevents an expired or superseded worker from completing or failing a reassigned job.
- Adds the bounded `run-job-worker` command for independently managed worker processes.
- Migrates existing `server-jobs.sqlite3` queues without replacing queued work.
- Keeps the SQLite adapter as the one-node reference backend; the fencing contract is
  ready for the later shared PostgreSQL repository.

## Fieldora 0.08.26 — trusted OIDC discovery and signing-key refresh

- Adds optional OpenID Connect discovery while retaining the pinned local-JWKS mode.
- Requires HTTPS discovery and JWKS endpoints and an exact match between discovered
  and configured issuer values.
- Bounds metadata downloads, request timeouts, and the configurable key-cache interval.
- Refreshes the signing-key set once when an otherwise valid token references an
  unknown key ID, supporting routine provider rotation without an unbounded retry loop.
- Continues to map `(issuer, subject)` to an enabled local user; provider claims never
  become Fieldora permissions and PBAC remains authoritative.

## Fieldora 0.08.25 — restored-root startup and upgrade validation

- Adds `fieldora-server-recovery validate-restored-root` for offline recovery drills.
- Requires all six authoritative Phase D server databases instead of silently creating
  missing state.
- Opens the recovered copy through the current access, Science, media, job, export,
  and search adapters so supported schema migrations execute before deployment.
- Rechecks SQLite integrity after migration and composes the complete server API
  without binding a network listener.
- Exercises `/api/v1/status` against the composed recovery copy.
- Writes an optional atomic, machine-readable readiness report.

## Fieldora 0.08.24 — verified one-node recovery

- Adds a dedicated `fieldora-server-recovery` operator command for backup, verification,
  and restore testing.
- Uses SQLite's online backup API for transaction-consistent snapshots of every
  authoritative server subsystem database.
- Includes local governed media and export payloads with exact size and SHA-256
  manifests.
- Rejects duplicate, unsafe, undeclared, missing, corrupt, or non-integral content.
- Restores only to a destination that does not exist, leaving the running source data
  untouched and making recovery drills non-destructive.
- Records S3 objects, TLS material, and signing/trust keys as explicit external
  dependencies that require provider-specific backup.

## Fieldora 0.08.23 — TLS-enabled one-node server

- Adds direct HTTPS serving with an explicit PEM certificate and private key.
- Requires TLS 1.2 or newer and sends HSTS on HTTPS responses.
- Refuses non-loopback listeners without TLS by default.
- Retains loopback HTTP for standalone development and provides an explicit insecure
  override only for operation behind a trusted TLS terminator.
- Rejects partial certificate configuration and closes the listener if certificate
  loading fails.
- Keeps certificate paths out of API responses and never accepts private-key material
  as a command-line value.

## Fieldora 0.08.22 — S3-compatible governed media storage

- Extracts governed media bytes behind a replaceable object-store contract while
  keeping the independent media registry authoritative.
- Keeps contained filesystem storage as the default standalone adapter.
- Adds an optional S3-compatible adapter for publication, exact range reads, and
  compensating deletion when metadata persistence fails.
- Sends SHA-256 metadata and MIME type with each object and retains opaque keys rather
  than object URLs in the media registry.
- Publishes resumable uploads only after declared length and SHA-256 validation.
- Adds explicit bucket, prefix, endpoint, and region server configuration using the
  standard SDK credential provider chain; credentials are never CLI arguments.

## Fieldora 0.08.21 — governed contract expiry reminders

- Adds a cursor-bounded queue for active contracts expiring inside a configurable
  one-to-365-day review window.
- Applies `administer_contracts` PBAC to every candidate before disclosure.
- Excludes already-expired, inactive, malformed-date, out-of-window, and unauthorized
  contracts.
- Adds a separate accessible Expiring workspace with refreshable review window.
- Keeps expiry review read-only; lifecycle changes still use the existing separately
  authorized contract-status operation.

## Fieldora 0.08.20 — delegated contract approval queue

- Adds a cursor-bounded approval queue containing only proposed contracts the
  authenticated identity may approve through `approve_contracts` PBAC.
- Lets an approver discover and act on proposals without granting the broader
  `administer_contracts` permission.
- Conceals proposals outside the approver's organization/project policy scope.
- Excludes proposals created by the requester, proposals already approved by the
  current identity, and contracts whose quorum is complete.
- Adds a separate accessible Approvals workspace to the limited web client.

## Fieldora 0.08.19 — contract approval quorums

- Adds a bounded one-to-ten approval quorum to proposed project contracts.
- Records every distinct approver and timestamp while the contract remains proposed.
- Rejects requester approval, duplicate approval, disabled identities, invalid quorum
  sizes, and lifecycle attempts that bypass remaining approvals.
- Creates no derived PBAC policy until the final required approval; final activation
  and all policies remain one atomic database transaction.
- Shows approval progress and quorum configuration in the limited web client.
- Retains the 0.08.18 single-approval fields after activation for compatible clients.

## Fieldora 0.08.18 — independent contract approval

- Adds optional proposed contracts that create no access policies before approval.
- Adds a separate `approve_contracts` PBAC action and approval API operation.
- Requires the approver to be a different enabled identity in the contract
  organization, even when the requester also holds approval permission.
- Atomically activates the contract and all derived PBAC policies in one
  access-control database transaction.
- Blocks direct activation and terminate/reactivate bypasses until independent
  approval records approver identity and time.
- Adds secure-by-default approval selection and proposed-contract actions to the web
  client.

## Fieldora 0.08.17 — contract administration web client

- Adds Contracts as a separate accessible navigation item in the limited web client.
- Adds bounded contract listing, explicit organization/project/subject/date fields,
  right selection, and active/suspended/terminated lifecycle controls.
- Uses semantic tabs, labelled controls, keyboard-visible focus, live status messages,
  responsive layout, and safe text-only rendering for server values.
- Keeps bearer credentials in session storage only and sends the administration
  purpose explicitly for every contract request.
- Retains the server as the enforcement boundary: opening or manipulating the client
  does not bypass `administer_contracts` PBAC.

## Fieldora 0.08.16 — governed contract administration API

- Adds authenticated API operations to create, list, inspect, suspend, terminate, and
  reactivate project contracts.
- Requires central `administer_contracts` PBAC for the target organization, project,
  and contract; local roles or external identity claims are not implicit authority.
- Conceals unknown and denied contract IDs with the same 404 response and filters
  cross-tenant records before disclosure.
- Adds cursor-bounded contract listings and bounded request bodies.
- Proves that an unauthorized caller cannot create a grant, a project administrator
  cannot cross projects or tenants, and remote suspension revokes derived access at
  the next PBAC decision.

## Fieldora 0.08.15 — recipient-encrypted exports

- Adds explicit X25519 recipient key generation; only the public JSON key is submitted
  to the server and persisted in the durable job.
- Encrypts the complete portable project ZIP with a fresh ephemeral X25519 key,
  HKDF-SHA256, and streaming AES-256-GCM.
- Authenticates the envelope header, ciphertext, recipient key identity, and final tag;
  wrong-key, truncated, and modified packages fail without publishing plaintext.
- Adds offline decryption to a new destination and refuses to overwrite an existing
  destination or implicitly replace recipient key material.
- Composes encryption with the existing Ed25519 attestation by signing the delivered
  ciphertext, allowing authenticity verification before decryption.

## Fieldora 0.08.14 — signed governed exports

- Adds explicit Ed25519 export-signing identity generation with a separately
  distributable trusted public-key file.
- Signs the SHA-256 of the complete governed project archive without changing the
  strict two-member portable package format.
- Persists detached attestation metadata in the isolated export registry and exposes
  it only through the same `download_export` PBAC decision as package bytes.
- Adds offline verification that rejects package tampering, altered attestations, and
  keys absent from the selected trust file.
- Keeps unsigned 0.06–0.08.13 packages compatible and never generates or replaces a
  private signing key implicitly.

## Fieldora 0.08.13 — project contract grants

- Adds one validated administration operation for a time-bounded, project-scoped
  contract and its PBAC policies.
- Maps only declared rights to their applicable resources and purposes: project
  viewing/search, export submission, job visibility, export download, and upload.
- Normalizes contract dates to UTC and rejects missing rights, unknown rights,
  unordered dates, naive timestamps, and subjects outside the organization.
- Adds immediate active, suspended, and terminated contract-state administration.
- Proves that contract access cannot cross projects and that suspension immediately
  conceals job results and previously generated export packages.

## Fieldora 0.08.12 — governed export lifecycle

- Adds independent `revoke_export` PBAC for immediate project-export withdrawal.
- Removes revoked payload bytes while retaining revocation and purge timestamps in the
  isolated export registry for operational audit.
- Adds deterministic expiry cleanup through `fieldora-server
  purge-expired-exports`.
- Rechecks lifecycle state immediately before reading payload bytes so a revoked or
  purged export fails closed even when a prior lookup succeeded.
- Migrates the 0.08.11 export registry in place and validates metadata preservation.

## Fieldora 0.08.11 — governed project-export jobs

- Adds the isolated authoritative `server-exports.sqlite3` result registry and a
  contained server-export payload root.
- Runs portable project generation through the durable leased job worker.
- Requires project-scoped `export` PBAC before submission, `view_job` PBAC before
  status/result disclosure, and `download_export` PBAC before every GET or HEAD.
- Returns a stable export ID, filename, byte count, SHA-256, and expiry without
  disclosing a filesystem path.
- Adds expiring, integrity-labelled, resumable byte-range downloads and preserves the
  portable format's explicit exclusion of original Library media.

## Fieldora 0.08.10 — durable authorized server jobs

- Adds the authoritative, isolated `server-jobs.sqlite3` queue.
- Adds transactional claims, expiring leases, bounded attempts, and lease recovery.
- Adds separately authorized job submission, status, and terminal output.
- Adds a deterministic search-rebuild worker and one-shot worker CLI.
- Proves that a submitter cannot read job output without `view_job` PBAC.

## Fieldora 0.08.9 — governed search projection

- Adds an isolated, rebuildable `server-search.sqlite3` FTS projection.
- Adds deterministic project/dossier projection rebuild tooling.
- Normalizes and bounds queries, result limits, and internal candidate counts.
- Evaluates every candidate through PBAC `search` before returning its title or snippet.
- Proves that matching text from a denied project produces no result or snippet.
- Registers search as a derived subsystem that may be rebuilt instead of backed up as
  authoritative data.

## Fieldora 0.08.8 — tamper-evident decision audit

- Adds a canonical SHA-256 predecessor chain for every PBAC decision event.
- Seals existing audit rows once during migration and chains new rows transactionally.
- Detects changed, missing, reordered, extra, or disconnected audit records.
- Adds a verification CLI and a bounded, organization-filtered audit API protected by
  `view_audit` PBAC.

## Fieldora 0.08.7 — pinned OpenID Connect verification

- Adds federated `(issuer, subject)` mappings to enabled local user identities.
- Adds strict RS256 JWT verification using a configured issuer, audience, and JWKS.
- Validates key ID, signature, expiry, not-before, issuer, audience, and subject.
- Rejects unmapped, disabled, malformed, incorrectly signed, or claim-invalid tokens.
- Keeps roles, contracts, object rules, and all authorization in local PBAC.
- Adds server flags and CLI mapping while leaving discovery and dynamic JWKS refresh
  for production adapter work.

## Fieldora 0.08.6 — interactive device authorization

- Adds short-lived device-code and human-readable user-code issuance.
- Stores only code hashes and expires pending authorizations after ten minutes.
- Requires an authenticated PBAC `enroll_device` decision for the requested project.
- Creates the device identity and project role only after approval.
- Exchanges the device secret exactly once for a revocable device credential.
- Returns authorization-pending without disclosing a credential and rejects replay.

## Fieldora 0.08.5 — project-bound device credentials

- Adds administrator-driven device enrollment for standalone and field clients.
- Creates an explicit device identity with an organization/project-scoped role.
- Issues a one-time-disclosed, hashed, expiring, and revocable device key.
- Uses the same API authentication boundary while retaining device identity in every
  PBAC decision and audit event.
- Proves that an enrolled device can see its project but not another project in the
  same organization.

## Fieldora 0.08.4 — scoped service credentials

- Adds service-identity API keys for integrations, workers, and controlled automation.
- Returns each high-entropy key once and stores only its lookup prefix and SHA-256.
- Enforces expiry, revocation, enabled state, and service identity kind on every use.
- Keeps API-key requests subject to the same PBAC decisions as interactive sessions.
- Adds CLI creation with organization/role assignment and credential-ID revocation.

## Fieldora 0.08.3 — governed resumable uploads

- Adds persistent upload sessions to the isolated server-media database.
- Adds PBAC-authorized upload creation and chunk continuation.
- Enforces upload ownership, strict contiguous offsets, declared sizes, and 8 MiB
  maximum chunks.
- Verifies SHA-256 before atomically publishing a completed media object.
- Preserves received offsets across process restarts and rejects overlapping, skipped,
  oversized, out-of-project, and integrity-invalid contributions.

## Fieldora 0.08.2 — governed resumable media

- Adds a separate authoritative `server-media.sqlite3` registry and contained media
  storage root.
- Adds server-side media registration with stable IDs, MIME type, size, and SHA-256.
- Adds PBAC-authorized `GET` and `HEAD` media delivery without storage-path disclosure.
- Adds single-range HTTP resume with 206/416 responses, `Content-Range`, ETag, and
  integrity headers.
- Returns the same 404 response for unknown and unauthorized media IDs.
- Registers the media database for migrations, integrity inventory, and catalog backup.

## Fieldora 0.08.1 — governed contribution and login hardening

- Adds per-client/username login throttling with generic failure behavior.
- Adds PBAC-authorized project and dossier mutation endpoints.
- Adds optional `If-Match` optimistic concurrency and HTTP 409 conflict responses.
- Applies one-megabyte request bounds and immediate SQLite write transactions.
- Preserves per-object audit decisions for allowed and denied mutations.

## Fieldora 0.08.0 — governed server vertical slice

- Adds the `fieldora-server` command with local user bootstrap and a loopback-safe
  one-node reference listener.
- Adds salted PBKDF2 password verification, high-entropy opaque bearer sessions,
  server-side token hashing, expiry, identity revalidation, and revocation.
- Adds versioned `/api/v1` status, session, identity, project, and dossier endpoints.
- Applies the central default-deny PBAC decision to every candidate project and
  dossier before it can enter an API response.
- Adds a responsive, limited-rights web client that has no direct database or object
  storage access.
- Adds security headers, non-cacheable API responses, bounded login bodies, generic
  credential failures, server/session tests, and reference deployment documentation.
- Keeps OIDC, device authorization, PostgreSQL, S3, TLS, rate limiting, distributed
  jobs/search, resumable media, and production hardening explicitly out of scope.

## Fieldora 0.07.0 — identity and PBAC foundation

- Adds users, groups, service identities, devices, organizations, scoped role
  assignments (including nested group membership), contracts, PBAC policies, and
  append-only decision audit records.
- Implements default deny, organization boundaries, action/resource/object/project
  scope, declared purpose, requested fields, attribute conditions, policy validity,
  contract validity, and explicit-deny precedence.
- Treats RBAC, ABAC, contracts, and object grants as inputs to one PBAC decision.
- Adds `decide()` and fail-closed `require()` application enforcement contracts.
- Registers the independent authoritative `access-control.sqlite3` subsystem for
  migrations, health, integrity, inventory, verified backup, and restore payloads.
- Adds **Settings → Access & Contracts** for local identity, role, contract, policy,
  and decision-audit administration.
- Documents that local desktop administration is not authentication and does not yet
  represent OIDC, MFA, sessions, tenant-isolated server enforcement, or legal signature.

## Fieldora 0.06.0 — portable projects

- Exports a selected project, stages, activities, resources, budget, dossiers,
  attached whiteboards, and board elements into a versioned portable package.
- Uses deterministic ZIP members and canonical JSON with a verified SHA-256 records
  checksum.
- Always excludes original Library media and asks explicitly whether stable Library
  references should remain.
- Records producer, project identity, counts, reference decisions, and a redaction
  report in the manifest.
- Provides import preview and fail, keep-existing, or replace collision policies.
- Applies imports through one revision-checked repository transaction and restores
  in-memory state after any failure.
- Rejects extra ZIP members, oversized members, unsafe compression ratios, unsupported
  formats, and checksum mismatches.
- Removes project-scoped records and orphaned boards safely without deleting Library
  assets.

## Fieldora 0.05.1 — incremental Science repository

- Moves the active Science persistence path from Qt into
  `infrastructure/database/science.py`.
- Gives all seven Science screens one application-owned `ScienceSession`.
- Stores projects, dossiers, artifacts, boards, elements, resources, activities,
  budgets, and links as independently identified records.
- Computes a database diff and issues record-level insert, update, and delete
  statements instead of deleting and rebuilding complete tables.
- Tracks per-record revisions and advances the database revision only when data
  actually changes.
- Rejects stale writers before any record mutation and reloads the complete snapshot
  deterministically after restart.
- Adds the incremental schema to the registered Science subsystem migration chain.

## Fieldora 0.05.0 — Science integrity

- Registers Science through the optional-subsystem lifecycle and uses one canonical
  application-level `subsystems/science.sqlite3` path.
- Adds subsystem health and SQLite integrity reporting for Science.
- Includes the authoritative Science database in verified catalog backups and records
  its checksum, size, and relative path in the backup manifest.
- Marks subsystem databases as authoritative in Maintenance inventory.
- Adds a dependency-free Science domain revision contract and application repository
  port for subsequent adapter extraction and synchronization.
- Adds database-wide optimistic revision checks so a stale Science process cannot
  silently overwrite newer work.
- Adds dossier search, edit, duplication, deletion, and safe preservation of linked
  Library assets and whiteboards.
- Persists moved whiteboard cards and SVG icons after selection-mode manipulation.

## Fieldora 0.04.0 — independent Science workspaces

- Places Projects, Dossiers, Animals, Plants & Flowers, Other Artifacts,
  Whiteboard, and Activity Calendar directly in the navigation pane.
- Adds Settings switches for every Library and Science workspace without
  deleting retained data.
- Adds project stages, stage-linked activities, required resources with
  estimated costs, and planned/spent budgets.
- Replaces the sticky-only board with persistent freehand, line, rectangle,
  ellipse, color, selection, undo, and sticky-note tools.
- Makes whiteboards named, independently saved documents that can be created,
  selected, renamed, attached to dossiers, and exported as SVG or PDF.
- Adds Library asset reference cards for images, videos, sounds, and documents,
  a built-in science/process symbol palette, and sanitized user-supplied SVG icons.
- Keeps Science records and workspace settings in the separate
  `science.sqlite3` database with WAL and bounded lock waiting.

## Fieldora 0.03.2 — startup repair and product rename

- Renamed the complete user-facing product identity from the previous name to Fieldora.
- Existing internal package and data-directory identities remain compatible with installed
  libraries and upgrade tooling.
- Restored the missing `QFormLayout` import that prevented the Science workspace and the
  desktop application from starting.
- Added an installer GUI smoke check that constructs the Science workspace.
- Added a source regression ensuring every Qt layout constructed by Science is imported.

## Fieldora 0.03.1 — documentation consolidation and audit

- Added one canonical documentation map and a generated runtime-help workflow.
- Consolidated historical build, repair, and validation notes under `docs/archive/`.
- Removed redundant authoring copies of Vision, Philosophy, and the Version 2 charter.
- Added the Science subsystem architecture and a software audit against Vision,
  Philosophy, Architecture, Coding Standard, Database design, and Roadmap.
- Recorded Science backup/health integration and UI-owned persistence as high-priority
  architecture gaps rather than presenting the 0.03 prototype as production-complete.

## Fieldora 0.01

- The product is now named **Fieldora**, beginning with version **0.01**.
- Added a first-class Science workspace with an editable local project register.
- Added an offline visual whiteboard for movable research notes and ideas.
- Added an activity calendar for fieldwork, analysis, review, and project milestones.
- Science records are stored within the active Aperture library and require no hosted service.

## Fieldora 0.02

- Science now has its own transactional `science.sqlite3` database instead of JSON storage.
- Existing 0.01 project, whiteboard, and calendar data is imported automatically.
- Added separate Animal, Plants & Flowers, and Other Artifacts registration screens.
- Artifact records include taxonomy names, date, location, dimensions, weight, colors,
  sex or life stage, quantity, flower diameter, notes, and stable identifiers.
- Indexed artifact categories and activity dates keep local searching and reporting scalable.

## Fieldora 0.03

- Added Science Dossiers as durable records in the independent `science.sqlite3` database.
- A dossier can belong to a project, remain independent, or become a project itself.
- Dossiers link selected photos, sounds, videos, and documents by stable public ID without
  copying media or opening the main library database.
- Notes, dimensions, weight, a calendar date, and an optional whiteboard doodle are stored
  together with each dossier.
- Dossier-to-project, dossier-to-media, calendar, and whiteboard relationships use foreign
  keys and indexed local tables. WAL mode, bounded busy waiting, and single-database write
  transactions avoid cross-database locking.

- Added a read-only platform snapshot for support and field validation.
- Added workflow-run aggregation over durable background jobs.
- Added backup SHA-256 and SQLite integrity auditing.
- Added Maintenance Center export for privacy-conscious JSON diagnostics.
- Completed platform-hardening regression coverage before the Version 1 RC cycle.

# Aperture 4.0.0.dev1 Build 33.5 — Analytics reporting expansion

## Interactive observation analytics

The Reporting workspace is now an Analytics workspace with overview, biodiversity, geography, time, quality, and report-generation views. It provides pie and bar charts for media composition, identified observations by photo/video/sound/document, taxonomic groups, countries, regions, capture months, and review status. Shared filters support media type, species group, country, region, review state, date range, and current-selection versus full-library scope. Chart values are clickable for drill-down, and the HTML report generator now exports the same analytics aggregates. All queries are read-only and preserve existing observation, library, export, and Activity Center behavior.

# Aperture 4.0.0.dev1 Build 33.5 — Phases 1–7 integrated release

## Media workspace production refactor

Build 33.5 now combines the media workspace framework, standard collapsible sections, dedicated Sounds/Videos/Documents center surfaces, permanently docked adaptive inspectors, and media-aware bottom actions with the previously approved Models page and Knowledge Sources category. Existing library, playback, overlay, enrichment, review, provenance, and installation behavior is retained.

# Aperture 4.0.0.dev1 Build 33.5 — Phase 6 Models Page

## Complete model workflow documentation

The Models workspace now exposes Purpose, Produces, Dependencies, Works With, Typical Workflow, Offline Ready, and live Runtime Health for every catalogued model. The model catalog contains explicit output documentation, while runtime status is derived from validated installation and dependency state. Existing model installation, licensing, activation, parameters, enrichment routing, offline execution, review, and provenance behavior are preserved.

This package also retains the approved Phase 7 Knowledge Sources separation.

# Aperture 4.0.0.dev1 Build 33.5

## Knowledge Sources separation

Build 33.5 introduces the approved resource taxonomy as the first production-refactor milestone. The desktop navigation now separates Core, AI Models, Knowledge Sources, Science, and Extensions. A dedicated Knowledge Sources workspace presents GBIF, iNaturalist, eBird, and Xeno-canto as optional scientific/reference providers rather than executable AI models.

GBIF remains optional and independent. Existing taxonomy import, regional acquisition, enrichment-source lifecycle, integration management, model installation, and AI inference routes are preserved. The workspace also documents the canonical flow: media → AI candidate → optional knowledge sources → Knowledge Base review → accepted observation.

# Aperture 4.0.0.dev1 Build 33.2

## Offline model runtime release

Build 33.2 is a clean-start Windows and Linux field-test release. No migration from earlier development libraries is included. Optional models and their dependencies are installed through Tools & Resources → Models. Installation may use the network or a complete local model package; after the model passes its health check, enrichment runs from Aperture-owned local artifacts without network access.

### Repairs

- Replaces the removed MegaDetector 6 URL with the maintained official MegaDetector 5a artifact.
- Stores MegaDetector weights in the model runtime instead of a temporary directory.
- Makes model health checks acquire required artifacts before publishing an installed marker.
- Forces optional-model enrichment workers into offline mode.
- Adds a common offline execution declaration to every supported model catalog entry.
- Keeps BioCLIP 2 and BioCLIP 2.5 Huge behavior from Build 33.1.

### Supported optional model families

BirdNET, SpeciesNet, MegaDetector, BioCLIP 2, BioCLIP 2.5 Huge, Perch 2, and BatDetect2 remain catalogued with isolated dependencies, license disclosure, and media compatibility.


## Build 33.3
Adds offline YOLO 11 detection/segmentation and Segment Anything ViT-B model providers.

## Build 34 — Exchange & Internationalization

- Added offline-first internationalization catalogs for English, Dutch, German, French, Spanish, Portuguese, and Italian.
- Added localized export language selection and Darwin Core Archive export.
- Added connector registry and offline preflight validation for Waarneming.nl, Observation.org, iNaturalist, and GBIF.
- Preserved explicit user control: no network upload occurs without a future authenticated connector adapter.
### Build 35 — executable region-classification workflow

- Photo enrichment can now run an installed bounding-box detector such as YOLO 11 and immediately pass every detected crop to an installed taxonomy classifier such as BioCLIP 2.
- The execution dialog enables this chained workflow by default when both compatible stages are installed.
- Detector boxes and classifier candidates are both retained, and every taxonomy candidate records the originating region, detector, label, and detector confidence.
## Fieldora 0.11.0 — Project & Work Management

- Replaced the former lightweight Science Projects page with a normalized,
  no-migration task and work-management module.
- Added list, Kanban, grid, Gantt, calendar, workload, dashboard, activity, and
  project-administration views.
- Added dependencies, recurring tasks, milestones, templates, comments,
  mentions, files and versions, time/capacity/PTO, RBAC, client portal previews,
  custom fields, agile metrics, and CSV, Excel, and PDF reports.
## Fieldora 0.11.1 — Science and Platform Navigation

- Reorganized the navigation into two stable roots: Science Workspace and
  Platform Management.
- Grouped scientific work into Research, Library, Scientific Records,
  Knowledge, and Analysis.
- Grouped administration into People & Governance, AI & Processing, Knowledge
  Configuration, Integrations, Library Administration, Operations, and
  Appearance.
- Replaced the uneven menu bar with File, Research, Data, Analyse, Collaborate,
  Platform, and Help menus. About Fieldora now lives under Help.
- Adopted the approved “Plants & Fungi” terminology and aligned Whiteboards,
  Research Calendar, Observation Register, Projects & Tasks, and Operations
  Center labels.
## Fieldora 0.11.2 — Windows Installation Verification Repair

- Fixed the Windows GUI installation smoke test retaining its temporary
  `science.sqlite3` until after the temporary directory cleanup began.
- The verifier now closes and schedules the Science workspace for deletion,
  processes Qt deferred-delete events, releases the Python reference, and runs
  garbage collection before leaving the temporary directory.
- BioCLIP resource installation and existing user libraries are unaffected.

## Fieldora 0.11.3 — Photo Path Search Repair

- Filename search now filters the gallery by partial filename or directory
  text from either the managed path or original import path.
- Starting a search leaves Latest Import mode and displays only matching
  catalog results.
- Search changes made during an active refresh are no longer discarded.

## Fieldora 0.11.4 — Incremental Media Import

- A second import of unchanged media now skips full-file hashing, image
  decoding, metadata extraction, FFmpeg probing, PDF inspection, and managed
  copy verification.
- The fast path applies consistently to photos, RAW files, sounds, videos, and
  documents under managed, linked, and hybrid storage policies.
- Bounded fingerprint validation prevents size-and-time matches from hiding
  changed content; mismatches return to authoritative SHA-256 processing.
- Import progress now identifies the current file and completed item count.

## Fieldora 0.11.5 — Staged Quarantine Ingestion

- Multi-user deliveries can now enter a separate quarantine workflow instead
  of becoming immediately visible governed media.
- Sealed submissions trigger independently leased security and integrity
  validation jobs, followed by bounded parallel processing batches.
- Access-contract ID, purpose, organization, project, submitter, relative
  source path, checksum, and validation evidence remain attached throughout
  staging.
- Malware, checksum, media-signature, unsafe-archive, and policy failures do
  not enter normal media routes.
- This release provides the one-node/reference staging adapter. PostgreSQL
  staging metadata and direct multipart object-store quarantine remain required
  before horizontal Kubernetes ingestion certification.
