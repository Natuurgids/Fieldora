# Offline updates

Aperture 0.17.3 adds a trusted-folder update workflow. Open **Settings → Check for Updates…** or **Help → Check for Updates…** and select the predefined folder, removable drive, mapped drive, or UNC share used by your administrator.

The selected location is saved per library in `update-settings.json`. Aperture expects `update-index.json`, the release ZIP, and optional release notes in that folder. It verifies product identity, update compatibility, and the package SHA-256 digest before offering the release.

When the user approves an update, Aperture first creates and verifies a catalog database backup. It then copies the package to the library's `updates/staging` directory, verifies the staged copy again, and writes `pending-update.json`.

A running desktop application cannot replace its own files safely. Close Aperture and run:

```powershell
.\scripts\install_staged_update.ps1 -StagingDirectory "D:\My Aperture Library\updates\staging"
```

The installer refuses to run while Aperture is active, rechecks the checksum, keeps a rollback copy of the prior application directory, and restores it if replacement fails. Configuration, library databases, originals, models, taxonomy resources, and caches live outside the application release and are not replaced.

## Update folder format

```text
Aperture-Updates/
  update-index.json
  NatureAI-Next-0.17.3-Aperture-Offline-Update-Manager.zip
  RELEASE_NOTES-0.17.3.md
```

Example index:

```json
{
  "format": "natureai-next.update-index",
  "format_version": 1,
  "product": "Aperture",
  "channel": "stable",
  "version": "0.17.3",
  "minimum_supported_version": "0.17.0",
  "package": "NatureAI-Next-0.17.3-Aperture-Offline-Update-Manager.zip",
  "sha256": "<package SHA-256>",
  "release_notes": "RELEASE_NOTES-0.17.3.md"
}
```

Only use update folders controlled by a trusted administrator. Version 0.17.3 validates SHA-256 integrity; first-party digital signature enforcement remains a release-hardening requirement before public internet distribution.

## Update history and cleanup

Open **Settings → Update History…** to review completed and failed native update attempts for the active library. A successful update removes its staged package after installation. Failed attempts retain their request status and installation log for diagnostics.
