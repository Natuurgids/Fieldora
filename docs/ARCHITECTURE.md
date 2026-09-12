# Fieldora architecture

## Architectural position

Fieldora is a domain-first modular platform. The same domain and application semantics support a native Qt desktop adapter and governed server/web adapters. Infrastructure can vary from local SQLite and filesystem storage to PostgreSQL, Docker services, storage nodes, and Kubernetes without redefining the domain model.

```text
Desktop / Web / API / CLI
          |
Application services and use cases
          |
Domain models, policies and invariants
          |
Ports / repository contracts
          |
SQLite / PostgreSQL / filesystem / services / external adapters
```

Dependencies should point toward domain and application contracts. Presentation and infrastructure are replaceable adapters.

## Modular ownership

Fieldora separates major capabilities into bounded modules such as Library, Observation, Science, Project, Dossier, Whiteboard, Knowledge, Facility, Administration, jobs, storage, mapping, and AI. The exact package layout may evolve, but ownership rules are stable:

- a module owns its authoritative records and invariants;
- relationships to another module use stable IDs and explicit services/contracts;
- one module does not acquire ownership merely by referencing another module's object;
- cross-module behavior is tested at the contract or integration boundary;
- presentation code must not become the only implementation of a business rule.

Library evidence remains Library-owned. Science and Dossier records can reference that evidence without copying or rewriting the original solely for organization. Dossiers can relate to whiteboards and other dossiers while those related objects retain their own lifecycle.

## Persistence

Desktop/local operation uses modular persistence with SQLite authorities where appropriate. Optional subsystems maintain independent migrations and lifecycle state. Cross-database foreign keys and write transactions spanning independent authorities are avoided.

Server deployments use PostgreSQL-backed repositories for governed shared state. Repository implementations must preserve the same application-level invariants and concurrency expectations as local implementations. Snapshot/revision operations are atomic at their repository boundary.

Authoritative state is distinguished from rebuildable indexes, caches, previews, thumbnails, and derived artifacts.

## Desktop adapter

The native Windows desktop application is a first-class Fieldora adapter, not a legacy compatibility shell. Qt screens use application services and repository contracts. Desktop can support local/offline workflows that do not require a server.

## Web/server adapter

The server authenticates protected requests, enforces organization isolation and authorization before disclosure or mutation, and exposes versioned APIs used by the browser client. Web UI logic may shape interaction but must not invent different domain rules.

Long-running or service-oriented work can use worker and operator infrastructure. Server deployments use explicit service identity and transport trust.

## Desktop/web parity

Parity is enforced in this order:

1. domain invariants;
2. application services and repository contracts;
3. governed API behavior;
4. desktop and web adapters.

A feature is not considered semantically complete merely because controls exist in both interfaces. Validation, authority, lifecycle, evidence relationships, provenance, deduplication, and failure behavior must also agree.

## Deployment architecture

### Native Windows Desktop

The desktop application uses the Windows installation/packaging path and local Fieldora capabilities. Docker Desktop is not required for the native desktop path.

### Windows and Linux Docker

The clean Docker deployment builds and runs a Fieldora server stack with PostgreSQL, API/server, worker, certificate renewal/trust infrastructure, and optional supporting capabilities. The Windows wrapper additionally integrates the Fieldora CA with the Windows current-user trust store. Linux adapts host checks and trust guidance while preserving the deployment contract.

### Kubernetes

The Kubernetes baseline is a minimal cloud-neutral Kustomize deployment. It uses hardened workloads, a restricted namespace posture, external Secret references, network policy, probes, and TLS ingress. Production data services such as PostgreSQL, S3-compatible object storage, and OpenSearch are treated as external dependencies rather than embedded assumptions.

### Offline and distributed capabilities

Fieldora supports offline model bundles, local/offline storage patterns, maps, linked originals, storage-node and Bastion patterns, and explicit synchronization workflows. These extend the platform without changing evidence ownership.

## Architecture history

Older root-level architecture documents contain Aperture/NatureAI Next design evolution and release-specific boundaries. They remain useful provenance. This document is the current platform-level architecture entry point; specialist documents continue to define deeper contracts where they remain applicable.
