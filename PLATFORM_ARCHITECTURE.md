# Fieldora Platform Architecture

This document records the durable server/platform decisions that complement `VISION.md`, `ARCHITECTURE.md`, and `ARCHITECTURE_DECISIONS.md`. The desktop application and the managed platform share scientific meaning and stable public identifiers, while deployment technology may differ.

## Scientific evidence is not owned by projects

The governed Library is the durable evidence boundary. An asset belongs to an organization/library first. Project context is optional and is represented as a relationship rather than as the reason an asset exists.

A Library asset may independently participate in:

- zero, one, or many projects;
- zero, one, or many collections/datasets;
- observations and dossiers;
- external/citizen/institutional submissions;
- expert review cases and determinations;
- exports and publications.

Projects organize work. They do not own or duplicate the scientific evidence they reference.

## Submission and expert review are first-class domains

Fieldora accepts governed evidence without forcing a project. A Submission records intake provenance such as contributor/source, rights, consent, collection/project context, and receipt state.

Expert interpretation is represented by Review Cases and immutable Determinations. Review cases are scoped to the evidence required for the review and may route by scientific domain, specialty, geography, or other capability. Experts do not require access to an unrelated project merely to evaluate permitted evidence.

AI remains advisory. Accepted scientific conclusions are explicit human/governed actions and preserve the history of earlier or competing determinations.

## Single-node convenience, multi-node correctness

A small installation may run on one host using Docker/Podman and one PostgreSQL instance. The same authoritative contracts must remain correct when the installation grows to many API nodes, workers, database clusters, object stores, search nodes, or physical sites.

No authoritative scientific meaning may depend on a particular container, process, or host. Stable identifiers, durable job state, leases/fencing, storage contracts, access policy, and service identity are designed for horizontal growth from the beginning.

This does **not** mean anonymous or ungoverned stateless services.

## Durable service identity

Every Fieldora service has a durable enrolled identity independent of its process/container lifetime. Typical identities include API nodes, job workers, database services, trust/renewal services, search nodes, and future storage/ingest services.

A service lifecycle is governed explicitly:

`enrolled -> active -> draining -> stopped -> revoked`

Revocation is authoritative even when cryptographic material has not yet expired. Unknown, unenrolled, disappeared, or revoked worker identities fail closed.

Planned maintenance drains a service before shutdown. Healthy services are not casually destroyed and recreated merely because a queue is temporarily empty.

## Mandatory internal mutual TLS

Fieldora service-to-service network communication uses mutual TLS at every installation size, including a single Docker host.

The clean reference deployment therefore requires PostgreSQL network clients to provide a trusted service certificate and rejects non-TLS network connections. Browser/user access uses HTTPS and the ordinary user authentication/PBAC boundary; internal service identity is separate from human identity.

Certificate identity does not replace authorization. A valid service certificate proves enrolled cryptographic identity; the Operator registry determines whether that identity is currently permitted to operate.

## Root trust and certificate renewal

The installation root CA is long lived and is not mounted into continuously running services.

A constrained service issuer is signed by that root and is the only signing material made available to the online renewal controller. Short-lived leaf certificates may be renewed in place without changing durable service IDs.

The reference platform supports renewal without routine process churn:

- the Fieldora HTTPS server detects replacement certificate/key material and loads it for subsequent connections;
- PostgreSQL certificate replacement is followed by `pg_reload_conf()` so its TLS identity changes without a container restart;
- worker and database clients use certificate paths in their PostgreSQL DSNs so subsequent connections use the renewed material;
- Operator certificate serial/expiry metadata is updated as renewal occurs.

Production installations may replace the local constrained issuer with institutional PKI, HSM, Vault, OpenShift certificate management, or another approved issuer while preserving the same service-identity and Operator contracts.

## Long-lived workers, short-lived leases

Worker process lifetime, certificate lifetime, and job-lease lifetime are deliberately different:

- service identity: durable;
- healthy process: long lived;
- certificate: short lived and renewable;
- job lease: short lived;
- fencing token: specific to one claim generation.

Workers remain warm while healthy and wait efficiently for work. A draining worker stops taking new jobs while allowing current work to finish or be safely relinquished. Fencing prevents a stale worker from committing after a replacement has acquired the job.

## Operator control plane

The Operator workspace is a separate infrastructure/governance surface, not ordinary scientific administration. It is API-backed and separately permissioned.

The Operator surface is responsible for progressively exposing:

- enrolled nodes and services;
- active/draining/stopped/revoked state;
- heartbeat/staleness and software/configuration identity;
- certificate serials, expiry, and renewal state;
- database, object-storage, search, worker, and queue health;
- storage used/free/allocated capacity;
- job queue depth, leases, retries, and oldest work;
- logs and correlation/diagnostic views;
- backup/restore state and recovery evidence;
- maintenance, drain, revocation, and upgrade readiness.

Optional subsystem degradation must not be presented as loss of authoritative Library/Science state. Fieldora distinguishes healthy, degraded, and unavailable capabilities.

## Database and storage topology

Logical database ownership is independent from physical topology. A small installation may place all logical PostgreSQL databases on one PostgreSQL service. A larger installation may move logical domains to different clusters without changing public IDs or domain ownership.

Likewise, the contained filesystem object adapter is suitable for a small installation, while larger installations may use shared S3-compatible object storage. The Library contract, checksums, provenance, and authorization boundary remain stable.

## Bulk ingest

Human browser upload is not the architecture for institutional-scale migration. Large imports use durable manifests/jobs, resumable processing, checksums, deduplication, backpressure, exception reporting, and parallel workers. A 200-million or billion-asset import must be restartable and idempotent rather than tied to one HTTP request or process lifetime.

## Facilities planning preserves reality

Current physical placement remains authoritative. Future layouts and relocation campaigns are planning/execution records and do not alter live placement merely because a plan exists.

Only an explicit final relocation/placement action may change authoritative physical location. Intermediate states such as removed, in-transit, staging, stored, placed, and displayed remain auditable workflow state.

Architectural PDFs, CAD/BIM material, and operational drawings remain governed Library assets rather than forming an independent document repository.

## Deployment portability

Docker Compose is the clean reference test deployment, not an architectural dependency. The same images/contracts should remain deployable through Docker, Podman, RHEL/UBI, OpenShift/Kubernetes, institutional VMs, or managed infrastructure.

Deployment tooling may become more sophisticated as scale grows. Scientific identity, provenance, policy, service identity, mTLS, lifecycle, and recovery semantics must not change because the orchestrator changes.
