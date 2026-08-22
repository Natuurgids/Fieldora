## V3.RC1 Full AI installation

Full AI installs and activates BioCLIP, pybioclip, TreeOfLifeClassifier, and Tree-of-Life resources together. No GBIF import or CSV is required for the default NatureAI classifier.

# Installing Fieldora on Windows

## Supported baseline

Fieldora 0.17.9 targets 64-bit Windows 11 and Python 3.11. The GUI profile is the recommended first installation. The FullAI profile adds the local AI dependencies and should be validated on the target NVIDIA system.

## Install

1. Extract the release ZIP to a stable folder. Do not run from the ZIP preview.
2. Open PowerShell in that folder.
3. For the current process, allow the local scripts: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
4. Run `./scripts/install_windows.ps1 -InstallProfile GUI`.
5. Start Fieldora from the created shortcut or `scripts/start_natureai_next.bat`.

The launcher and internal command names intentionally remain Fieldora Engine compatible. Existing libraries and resource packages do not need conversion.

## Full local AI profile

Run `./scripts/install_windows.ps1 -InstallProfile FullAI`. After installation, use Settings → Health Check and Settings → AI Resources to confirm the active model, provider, prompt set, and taxonomy resources. A successful Python installation alone does not prove CUDA inference is working.

## Repair or uninstall

Use `scripts/repair_windows_integration.ps1` to rebuild shortcuts and Windows registration. Use `scripts/uninstall_windows.ps1` to remove the application integration; libraries and source photographs are preserved unless an explicit data-removal option is selected.

## Automatic full installation when the extraction folder is unknown

Use this method for a **full installation** from the extracted release package when you are not sure which folder contains `scripts\install_windows.ps1`. It searches drive `D:` for the installer, changes to the release root, and starts the FullAI installation.

Close Fieldora before running the installer. Open PowerShell and run:

```powershell
$script = Get-ChildItem "D:\" -Filter install_windows.ps1 -Recurse -ErrorAction Stop |
  Select-Object -First 1

Set-Location $script.Directory.Parent.FullName

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\scripts\install_windows.ps1 `
  -InstallProfile FullAI `
  -TorchBuild CUDA124 `
  -DefaultLibrary "D:\NatureAI-Libraries\TestLibrary" `
  -SkipDeploymentPreflight
```

This performs a full install or reinstall into the `natureai-next` Conda environment. The `-SkipDeploymentPreflight` option is included for this 0.17.9 package because its early preflight may resolve the Windows Store `python` alias before Conda is initialized. The installer still runs its normal package installation and verification steps.

If more than one extracted release exists on `D:`, remove or rename older copies first, or replace `"D:\"` with the specific parent folder containing the intended release.

## CMD installation launcher

For most Windows users, the recommended path is to extract the release and double-click `Install Fieldora.cmd` in the release root. It starts the FullAI installer with CUDA 12.4 support and prompts for an optional default library. The command window remains open when an error occurs so the message can be reviewed. `Repair Fieldora.cmd` and `Uninstall Fieldora.cmd` provide matching maintenance entry points.


## Recommended interactive or unattended installation

Double-click `Install Fieldora.cmd`. The installer asks for the storage drive rather than a technical library path. It explains that the Fieldora Library contains the SQLite database, metadata, thumbnails, backups, and managed photographs and therefore grows over time. After a drive is selected, the installer creates `<drive>:\Fieldora-Library` automatically or offers to reuse an existing valid Fieldora Library.

Unattended examples:

```cmd
Install Fieldora.cmd /silent /drive=D /profile=FullAI /useexisting
Install Fieldora.cmd /silent /drive=D /profile=GUI /createnew
Install Fieldora.cmd /silent /library="E:\Research\Fieldora-Library" /profile=FullAI
```

Supported options include `/silent`, `/drive=`, `/profile=`, `/torch=`, `/library=`, `/useexisting`, `/createnew`, `/repair`, and `/skippreflight`.

## Python runtime bootstrap

A separate Python installation is not required. If Miniconda or Anaconda is not present, the Fieldora installer downloads the official Miniconda Windows installer, verifies its published SHA-256 checksum, installs it for the current user, and then creates the isolated `natureai-next` Python 3.11 environment. For offline deployment, pass `-MinicondaInstallerPath` and optionally `-MinicondaSha256` to `scripts\install_windows.ps1`. Use `-SkipCondaBootstrap` only when deployment policy requires Conda to be installed separately.

