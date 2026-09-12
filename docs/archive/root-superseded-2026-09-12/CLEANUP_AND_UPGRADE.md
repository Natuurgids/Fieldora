# Cleanup and upgrade guide

## Authoritative baseline

Use `NatureAI-Next-0.11.1-Windows-Integration.zip` as the authoritative repository baseline for subsequent work.

## Safe to keep

Do not remove:

- `D:\NatureAI-Libraries\`
- source photograph directories such as `D:\NatureAI-TestData\` or `D:\Wildlife\`
- model archives
- backups
- exports
- the NatureAI Legacy installation and its `nature-ai` Conda environment

## Safe to remove after verification

Old extracted source folders such as:

- `D:\natureai-next-post2`
- `D:\natureai-next-post3`
- `D:\natureai-next-post4`
- `D:\natureai-next-post5`
- `D:\natureai-next-post6`
- `D:\natureai-next-hotfix`
- `D:\natureai-next-old`

Use `scripts\cleanup_old_builds.ps1` for a conservative dry run first.

## Recommended baseline location

Extract the release to:

```text
D:\natureai-next
```

Install or upgrade in place with:

```powershell
.\scripts\install_windows.ps1 -InstallProfile FullAI -TorchBuild CUDA124
```

The installer reuses the existing `natureai-next` environment unless `-RecreateEnvironment` is supplied.

## 0.11.1 launcher upgrade

Installing 0.11.1 replaces the machine-local launcher scripts and recreates the selected Windows shortcuts. It preserves `%APPDATA%\NatureAI\NatureAI Next\launcher.json`, so an existing default library remains selected. Use **NatureAI Next - Select Library** to change it.

The uninstaller removes launcher scripts and shortcuts. It removes the saved launcher configuration only when `-RemoveApplicationData` is explicitly supplied. Libraries and source photographs are never removed.

## 0.11.2 Windows registration upgrade

Installing 0.11.2 recreates the existing launchers and registers NatureAI Next in Windows Installed Apps. The repair action only restores Windows integration. It does not reinstall dependencies and does not touch libraries, photographs, backups, exports, or model archives.


## V3.RC1F5 legacy cleanup utility

Run `Cleanup Old Aperture Data.cmd` without arguments to produce a report only.

Examples:

```powershell
.\scripts\cleanup_legacy_data.ps1 -Mode Report -DataRoot D:\ApertureData
.\scripts\cleanup_legacy_data.ps1 -Mode Caches -DataRoot D:\ApertureData
.\scripts\cleanup_legacy_data.ps1 -Mode Complete -DataRoot D:\ApertureData
```

Shared Hugging Face and Torch caches require the additional `-IncludeSharedModelCaches` switch. The utility never scans arbitrary photo libraries and excludes the current data root.
