# Installer and repository cleanup notes

This document tracks the certified path dependencies that must be preserved while Fieldora reorganizes installation and deployment assets by target.

## Safety constraints

- Preserve historical documentation rather than deleting it.
- Keep certified public/root installer entry points compatible until workflows, script-to-script downloads, documentation, and raw-download references are updated atomically.
- Do not change native desktop behavior while reorganizing Docker/server material.
- Treat `docs/installation/` as the current installation documentation surface.
- Keep Windows Desktop, Linux Desktop, Windows Docker, Linux Docker, Kubernetes, and OpenShift as explicit deployment targets rather than collapsing them into one generic installer.
- Reuse shared implementation where appropriate, but keep platform-specific packaging, manifests, workflows, and certification explicit.

## Current certified baseline

The installer default-source correction is complete: the clean Docker installers now default `FieldoraRef` to `main`.

The current deployment tree already contains:

- `deployment/bootstrap-handoff/`
- `deployment/container/`
- `deployment/kubernetes/`
- `deployment/storage-node/`
- deployment reference JSON files.

The Kubernetes surface currently consists of `deployment/kubernetes/README.md` and `deployment/kubernetes/base/`. No OpenShift deployment directory is currently present.

## Root installer dependency graph

The following root files are certified entry points and therefore must not simply be renamed or deleted:

- `Install-Fieldora.ps1`
- `Install-Fieldora-Paired.ps1`
- `Install-Fieldora-Clean.ps1`
- `Install-Fieldora-Clean-Windows.ps1`
- `Install-Fieldora-Clean-Linux.ps1`
- `Install-Fieldora-Bootstrap-Handoff.ps1`
- `Install-Fieldora-Offline-Model.ps1`

`.github/workflows/docker-installer-certification.yml` explicitly watches and parses the five clean-install helper paths at repository root. Its contract tests also read the core, Windows, and Linux clean installers directly by those paths.

`.github/workflows/install-profile-certification.yml` explicitly watches the root selector, paired installer, Windows clean installer, and Linux clean installer. It certifies that `Install-Fieldora.ps1` delegates to the platform clean installers by their current root names.

Because these workflows encode exact paths and the wrapper scripts download or invoke other root scripts, a physical move must update all consumers in the same branch and retain stable compatibility entry points for existing raw GitHub URLs.

## Desktop status

`.github/workflows/fieldora-qt-certification.yml` runs the Qt desktop application offscreen on Ubuntu and certifies the existing Python/PySide6 desktop code path. This demonstrates Linux runtime compatibility of the Qt application code, but it is not a native Linux desktop installer or package.

No dedicated Linux desktop packaging implementation was identified in the current repository inventory under common packaging terms such as AppImage, Debian package, or PyInstaller. Therefore Linux Desktop remains an explicit missing packaging/installer adapter rather than being represented by `Install-Fieldora-Clean-Linux.ps1`, which is the Linux Docker/server installer.

Windows Desktop must remain separate from Windows Docker for the same reason: Docker is a server/runtime deployment adapter, not the native desktop product.

## Kubernetes and OpenShift status

`deployment/kubernetes/base/` is the current cloud-neutral Kubernetes baseline. OpenShift must be added as a first-class deployment target without duplicating the entire Kubernetes implementation unnecessarily.

No current repository implementation was identified for OpenShift-specific `Route` resources, SCC compatibility, or a dedicated `deployment/openshift/` surface. OpenShift certification must therefore be added explicitly rather than inferred from Kubernetes certification.

A preferred shape, subject to the exact manifest dependency review, is:

```text
deployment/
  desktop/
    common/
    windows/
    linux/
  docker/
    common/
    windows/
    linux/
  kubernetes/
    base/
    overlays/
  openshift/
    base/
    overlays/
```

Existing deployment directories such as `bootstrap-handoff`, `container`, and `storage-node` must be classified before any rename so their consumers are not silently broken.

## Migration sequence

1. Keep current root installer URLs working.
2. Introduce deployment-target implementation directories without changing installer behavior.
3. Convert root installer files to thin compatibility/bootstrap entry points only after their implementation has moved and certification covers both paths.
4. Update workflow path filters, direct file reads, script-to-script downloads, documentation, and raw GitHub references in the same change that moves implementation.
5. Add native Linux Desktop packaging from the existing Qt/application semantics; do not fork domain behavior.
6. Add OpenShift manifests/overlays from the Kubernetes baseline where compatible, with explicit OpenShift security and routing certification.
7. Only remove obsolete compatibility paths after a separately reviewed deprecation window; preserve provenance in the archive rather than deleting historical material.

## Next atomic changes

The next safe implementation changes should be split so structural relocation is not mixed with new platform behavior:

- Docker layout: introduce `deployment/docker/` implementation paths while retaining root compatibility wrappers and update Docker/install-profile certification atomically.
- Linux Desktop: add packaging/installer assets and certification as a separate feature change.
- OpenShift: add `deployment/openshift/` plus OpenShift-specific certification as a separate feature change.

This ordering keeps the repository reorganization reversible and allows each deployment target to prove parity independently.
