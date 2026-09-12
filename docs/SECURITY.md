# Fieldora security

Security is part of Fieldora's domain and deployment architecture. Presentation-layer hiding is not an authorization boundary.

## Authorization

Governed deployments use default-deny policy-based access control (PBAC). Roles, attributes, contracts, organization membership, object grants, and policy rules are inputs to a single authorization decision model.

Protected server operations authenticate the caller, establish organization context, and authorize candidate objects before disclosure or mutation. Missing authority and cross-organization access fail closed.

## Organization isolation

Organization ownership is explicit for governed shared records. APIs and repositories must not reveal another organization's object merely to return a more descriptive authorization error. Tests should cover cross-organization reads and writes as well as permitted paths.

## Service identity and transport trust

Docker/server deployments use durable service identities with short-lived certificates for API, worker, PostgreSQL, and renewal roles. HTTPS is mandatory for the browser/API listener. PostgreSQL network traffic requires TLS and trusted client certificates in the certified clean-install architecture.

The long-lived installation root CA private key is kept out of running service containers. Online renewal uses constrained issuer material. Certificate renewal should not require changing service identity.

## Secrets

Credentials, private keys, session tokens, database passwords, and environment-specific secret values must not be committed to the repository. Deployment manifests reference external or generated secrets.

Bootstrap administrator credentials are temporary handoff material. Operators should rotate or remove bootstrap credentials according to the applicable deployment procedure.

## Sessions and credentials

Server authentication uses expiring session/token mechanisms. Raw bearer tokens should not be persisted as authoritative credentials. Credential handling must avoid logging secrets or placing them in URLs and documentation.

## Evidence security

A Dossier, Project, Science record, or web route does not gain authority over Library media simply because it links to that media. Authorization and ownership checks follow the owning module's contract.

## Installer security

Clean Docker installation is intentionally destructive within its selected installation root and must state that scope before proceeding. Installers verify required host capabilities and certify the resulting runtime rather than silently weakening TLS or using insecure HTTP fallbacks.

Offline model provisioning is explicit. Verified local bundles are preferred in restricted environments; installer paths must not introduce hidden network acquisition when an offline contract is selected.

## Kubernetes security baseline

The Kubernetes baseline uses restricted pod-security posture, non-root execution, no privilege escalation, read-only root filesystems where specified, dropped Linux capabilities, disabled automatic service-account token mounting, default-deny network policy, external Secret references, and TLS ingress.

## Reporting security defects

Treat accidental disclosure, authorization bypass, organization-boundary failure, secret exposure, provenance loss, and trust-store weakening as security issues even when the affected feature otherwise works.
