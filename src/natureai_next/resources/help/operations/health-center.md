# Aperture Health Center

The Health Center is the Version 1 control point for checking whether an open Aperture library is safe to continue using.

Open **Settings → Health Check** or choose **Tools → Health Check…**.

## Checks performed

A normal health check verifies:

- SQLite quick integrity and foreign-key consistency;
- `library.json` identity and readability;
- presence of originals, sidecar, cache, index, backup, and temporary directories;
- practical write access and available free space on the library volume;
- availability and age of verified database backups;
- availability of the configured offline update source;
- stale `.tmp` and `.part` files in the library temporary workspace;
- presence of rebuildable thumbnail, preview, and vector-index locations.

Choose **Run Full Database Check** for SQLite's complete integrity scan. This can take significantly longer on a large library.

## Status meanings

- **Healthy**: no error-level condition was detected.
- **Usable with attention**: warnings exist, such as no recent backup or no configured update source.
- **Action required**: the database, manifest, storage, or another authoritative component has an error.

A warning does not necessarily prevent work. An error should be resolved before importing or editing more material.

## Repair Safe Items

**Repair Safe Items** only performs conservative, rebuild-safe actions:

- recreates missing standard library directories;
- removes stale `.tmp` and `.part` files from the library temporary workspace.

It never edits original photographs, confirmed metadata, taxonomy records, observations, or the SQLite database. Aperture deliberately does not attempt an automatic in-place database repair. Use a verified backup and the Restore workflow when database integrity fails.

## Recovery actions

The Health Center provides direct access to:

- **Back Up Library…**
- **Restore Library…**
- **Check for Updates…**

After a restore or application update, reopen the library and run a full health check.
