# Installer and repository cleanup notes

This branch continues the post-parity repository cleanup after documentation consolidation.

## Safety constraints

- Preserve historical documentation rather than deleting it.
- Keep the certified Docker installer paths at repository root until workflows and raw-download references can be moved atomically.
- Do not change desktop installation behavior while reorganizing Docker/server material.
- Treat `docs/installation/` as the current installation documentation surface.

## Identified installer follow-up

The clean Docker installer entry points still default `FieldoraRef` to the historical `feature/versioned-facility-floorplans` branch. Current documentation explicitly passes `-FieldoraRef main`. A narrow installer-default correction is required, but should be certified independently from documentation archival and path relocation.
