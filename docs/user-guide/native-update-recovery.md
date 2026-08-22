# Automatic updates and recovery

Aperture completes verified updates and library restores automatically. End users do not need PowerShell, Command Prompt, or manual file copying.

## Install an offline update

1. Open **Settings → Check for Updates…**.
2. Select the approved offline update folder.
3. Review the release notes and approve staging.
4. Choose **Yes** when Aperture asks to restart and install.

Aperture creates a verified library backup, starts its background update helper, closes, installs the package, validates the installed version, and opens the same library again.

## Restore a verified backup

1. Choose **Restore Library…**.
2. Select a backup with its checksum manifest.
3. Approve the emergency pre-restore backup.
4. Choose **Yes** when Aperture asks to restart and restore.

The background recovery helper waits for Aperture to close, verifies the staged database, preserves a rollback copy, restores the catalog, and opens the library again.

## Failure handling

Update and restore status is recorded in the staging request and log files. A failed restore automatically replaces the prior database from its rollback copy. The PowerShell scripts remain developer and emergency-support tools only; the normal user workflow never requires them.
