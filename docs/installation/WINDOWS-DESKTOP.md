# Windows Desktop installation

This path installs the **native Fieldora desktop application**. It is separate from the Windows Docker/server installation.

## When to use it

Use the desktop path when you want the native Qt application, local/offline workflows, direct workstation use, local libraries, AI capabilities installed for the workstation, or desktop administration and research tools.

Docker Desktop is not required for the native desktop path.

## Current installer lineage

The repository still contains Windows installer and packaging assets whose filenames use the earlier Aperture / NatureAI Next naming. These are part of the product's historical evolution and should not be confused with the clean Docker installer.

Current desktop installation tooling includes the Windows installation scripts under `scripts/`, packaging/build tooling, and user-facing Windows launcher assets where present. The existing Windows source/install procedure supports profiles such as GUI and FullAI and keeps the application environment separate from unrelated Python installations.

## Data safety

Desktop install, repair, and uninstall procedures must treat user libraries, source photographs, model archives, backups, and exports as user-owned data. Removal of application/runtime components must not imply deletion of evidence libraries.

Before performing a destructive cleanup, verify the exact target path and use the applicable backup/recovery procedure.

## Architecture

The desktop UI is an adapter over Fieldora application/domain behavior. Native desktop workflows must preserve the same object identity, evidence, provenance, project, dossier, and governance semantics used by the server/web adapters where those capabilities overlap.

## Developer/source installation

For repository development, use the maintained Windows scripts and profiles in `scripts/` rather than Docker instructions. Historical `INSTALLATION.md` contains detailed source-install lineage, but it also includes superseded release-specific material; this guide is the current entry point until that material is fully decomposed into current and archive documentation.
