# Fieldora documentation

This is the canonical documentation map for the current Fieldora platform.

## Current product truth

- [Vision](VISION.md) — what Fieldora is for and where it is going.
- [Philosophy](PHILOSOPHY.md) — principles that constrain product and engineering decisions.
- [Architecture](ARCHITECTURE.md) — current domain, application, adapter, persistence, and deployment architecture.
- [Security](SECURITY.md) — authorization, organization isolation, service trust, transport security, and secret handling.
- [Development](DEVELOPMENT.md) — repository rules, parity requirements, certification, and change workflow.
- [Installation](installation/README.md) — choose the correct desktop, Docker, Kubernetes, or offline deployment path.

## Installation paths

- [Windows Desktop](installation/WINDOWS-DESKTOP.md)
- [Windows Docker](installation/WINDOWS-DOCKER.md)
- [Linux Docker](installation/LINUX-DOCKER.md)
- [Kubernetes](installation/KUBERNETES.md)
- [Offline deployment](installation/OFFLINE.md)

The Windows Desktop and Windows Docker paths are deliberately separate. Desktop is the native Qt application. Docker is the governed Fieldora server/web stack with PostgreSQL and service infrastructure.

## Detailed reference documentation

Existing specialist documents remain useful where they describe a bounded subject, including access control, server architecture, Science persistence, portable project packages, storage, deployment, and user workflows. When specialist documentation conflicts with the current documents above, the current documents define intended platform-level behavior and the implementation/tests determine actual behavior.

## Historical documentation

Fieldora evolved from Aperture and NatureAI Next. Root-level files and `docs/archive/` contain important design provenance, field-validation notes, old release procedures, audits, and migration history. They are retained intentionally, but version-specific historical instructions must not be presented as current installation or deployment guidance.

## Documentation maintenance rules

1. Maintain one current entry point per subject and link to it rather than copying instructions.
2. Use **Fieldora** for current platform documentation; preserve former product names only when discussing history or filenames that still use them.
3. Keep domain rules independent of desktop/web presentation details.
4. Document both native desktop and server/web deployment paths explicitly.
5. State destructive installer behavior prominently.
6. Keep credentials, private keys, tokens, and environment-specific secrets out of documentation and source control.
7. Move superseded release evidence to `docs/archive/` rather than rewriting history.
8. Update documentation in the same change that changes an architectural or operational contract.
