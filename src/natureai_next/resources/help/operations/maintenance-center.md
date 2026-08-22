## V3.RC1 NatureAI maintenance

Maintenance Center can download/resume BioCLIP resources, import a complete local folder, repair the Full AI environment, prime TreeOfLifeClassifier resources, validate compatibility, and activate the NatureAI Tree-of-Life profile.

# Aperture Maintenance Center

Aperture Maintenance Center is the visible companion application for maintenance operations that must continue while the main Aperture window is closed.

## Updates

When Aperture hands off an update, Maintenance Center remains visible and shows these stages:

1. verifying the staged package;
2. waiting for Aperture to close;
3. waiting for the library lock to be released;
4. installing the package;
5. verifying the installed version;
6. relaunching Aperture.

If installation fails, Maintenance Center remains visible with an error message and the update log remains in the library staging folder.

## Backup and restore

Maintenance Center lists verified database backups and supports creating, verifying, deleting, and restoring them. Restore can be performed with an emergency backup or, after explicit confirmation, without one.

## Safety boundaries

Maintenance Center never removes a lock owned by a live process. Original photographs and linked media are not modified by database backup or restore operations.


## Operational locations

The Maintenance Center shows the active library root, SQLite database, library manifest, backup folder, cache, temporary workspace, and application log location. Each location can be copied or opened in Windows Explorer. For a typical library the operational database is `D:\NatureAI-Libraries\<LibraryName>\library.sqlite3`.

## Offline map package acquisition

Use **Manage Offline Maps** to load a configured HTTPS catalog or local catalog JSON file, browse continent/country/region/province coverage, and install verified MBTiles packages.

Aperture displays download, installed, temporary-working-space, and free-space estimates before acquisition. Large packages trigger a recommendation to download in regional increments. For complete prepared collections, use **Import Map Bundle** and select a verified `.apkg` file.

Installed map packages can be enabled, disabled, updated, or removed. Removal reclaims only map-package storage and never deletes authoritative coordinates or observations.
