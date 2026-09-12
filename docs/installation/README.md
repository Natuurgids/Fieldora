# Installing Fieldora

Fieldora has multiple supported installation/deployment paths. Choose based on how you intend to use the platform; do not treat the native desktop installer and Docker installer as interchangeable.

| Use case | Guide |
| --- | --- |
| Native Windows desktop application | [Windows Desktop](WINDOWS-DESKTOP.md) |
| Fieldora web/server stack on Windows | [Windows Docker](WINDOWS-DOCKER.md) |
| Fieldora web/server stack on Linux | [Linux Docker](LINUX-DOCKER.md) |
| Cluster/orchestrated deployment | [Kubernetes](KUBERNETES.md) |
| Restricted-network / offline deployment | [Offline](OFFLINE.md) |

## Desktop versus server

**Windows Desktop** installs the native Qt application and its local environment/integration. It is appropriate for personal/offline use and desktop workflows. Docker Desktop is not required for that path.

**Docker** installs the governed Fieldora server/web environment. The clean installer creates a server stack including PostgreSQL and Fieldora services. It is intentionally destructive inside the selected install root when performing a clean installation.

Both paths belong to the same Fieldora platform. They should preserve the same domain semantics even though their deployment and presentation layers differ.

## Current script locations

The clean Docker installer scripts currently remain at repository root because certification workflows and helper downloads reference those paths:

- `Install-Fieldora-Clean.ps1`
- `Install-Fieldora-Clean-Windows.ps1`
- `Install-Fieldora-Clean-Linux.ps1`
- `Install-Fieldora-Bootstrap-Handoff.ps1`
- `Install-Fieldora-Offline-Model.ps1`

A future repository-layout change may relocate them under `deployment/docker/`, but such a move must update all workflow and download references atomically.

## Historical installation documents

Older root-level installation and cleanup guides contain NatureAI Next / Aperture version-specific procedures. Use them only for historical or migration investigation unless this documentation map explicitly references a procedure.
