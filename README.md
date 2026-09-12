# Fieldora

Fieldora is an offline-first evidence, nature, and research platform with two primary user-facing adapters: a native Windows desktop application and a governed web/server application. Both are expected to preserve the same domain, scientific, evidence, provenance, project, workflow, and access-control semantics.

The project grew from the Aperture / NatureAI Next lineage. Historical documents keep that provenance, but current product documentation uses **Fieldora** as the platform name.

## Choose how you want to run Fieldora

| Goal | Installation path |
| --- | --- |
| Native Windows desktop application | [Windows Desktop](docs/installation/WINDOWS-DESKTOP.md) |
| Web/server stack on Windows with Docker Desktop | [Windows Docker](docs/installation/WINDOWS-DOCKER.md) |
| Web/server stack on Linux with Docker Engine | [Linux Docker](docs/installation/LINUX-DOCKER.md) |
| Orchestrated infrastructure | [Kubernetes](docs/installation/KUBERNETES.md) |
| Offline / restricted-network deployment | [Offline deployment](docs/installation/OFFLINE.md) |

The native desktop installer and Docker installer are separate installation paths. Installing or maintaining one does not imply replacing the other.

## Start here

- [Documentation map](docs/DOCUMENTATION.md)
- [Vision](docs/VISION.md)
- [Philosophy](docs/PHILOSOPHY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Development](docs/DEVELOPMENT.md)
- [Installation guide](docs/installation/README.md)
- [User guide](docs/user-guide/README.md)

## Architecture in one paragraph

Fieldora follows domain-first modular architecture. Domain invariants and application services are authoritative; desktop, web/API, persistence, Docker, Kubernetes, and external integrations are adapters. Module ownership is explicit, cross-module relationships use stable identifiers and contracts, and a presentation layer must not invent alternative business rules. Offline operation, evidence provenance, user control, default-deny authorization, and recoverable persistence are architectural requirements rather than UI features.

## Repository areas

- `src/natureai_next/` — current implementation packages and adapters.
- `tests/` — unit, contract, integration, migration, parity, and certification tests.
- `scripts/` — development, installation, verification, migration, and operational tooling.
- `deployment/` — deployment assets, including container, Kubernetes, bootstrap-handoff, and storage-node material.
- `docs/` — current documentation plus historical evidence under `docs/archive/`.
- `.github/workflows/` — certification workflows used to prove architectural and deployment contracts.

## Documentation status

Documents under `docs/` identified by the [documentation map](docs/DOCUMENTATION.md) are the current entry points. Older root-level and archived documents may contain valuable design history, version-specific procedures, or migration evidence, but should not be treated as current installation instructions unless the documentation map explicitly points to them.
