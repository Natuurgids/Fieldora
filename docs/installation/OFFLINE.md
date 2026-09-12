# Offline and restricted-network deployment

Offline operation is a Fieldora architectural goal, not a separate product edition. The exact capabilities available offline depend on which models, maps, taxonomy resources, storage, and deployment assets have been provisioned locally.

## Desktop

The native desktop application is designed to keep local evidence and installed capabilities usable without continuous network access. Local libraries remain authoritative for their owned data.

## Server/Docker

The server stack can be deployed with locally prepared source/artifacts and optional verified offline model bundles. Use `Install-Fieldora-Offline-Model.ps1` for the certified local model provisioning path where applicable.

An offline-model workflow should not silently fall back to internet model acquisition. Signature and malware-scan requirements can be enabled when the deployment policy requires them.

## Storage and synchronization

Fieldora supports patterns for local/offline storage, storage nodes, linked originals, and explicit synchronization. Availability of a physical original is separate from the stable identity and metadata describing the evidence.

Synchronization must preserve identity, provenance, ownership, and conflict semantics. It is not permission to duplicate or rewrite another module's authoritative evidence.

## Maps and reference data

Offline maps and other reference packages are optional capabilities. They should be provisioned and updated as independently managed resources so a missing network connection does not prevent existing local data from being interpreted.

## Preparing an offline deployment

Before disconnecting the target environment:

1. obtain the required Fieldora source/release artifacts;
2. obtain and verify required container images or build inputs;
3. prepare approved model bundles and signing material where used;
4. prepare map/taxonomy/reference packages needed by the workflow;
5. prepare external database/object-search infrastructure or local equivalents required by the selected deployment;
6. document trust roots, credentials, backup destinations, and recovery procedure;
7. validate the complete installation in a network-restricted test environment.

Do not store operational credentials or private signing/CA keys in the repository merely to simplify offline installation.
