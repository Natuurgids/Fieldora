## Aperture V3.RC1F1 quick start

After installing Full AI, open **AI Resources** and verify that the BioCLIP model and Tree of Life classifier are ready. Select photographs in Library and start AI Review. Import GBIF only when independent taxonomy lookup or result enrichment is wanted.

# NatureAI Next Windows Quick Start

```powershell
# 1. Extract the repository, then open PowerShell in its root.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 2. Install the normal desktop profile in an isolated Python 3.11 environment.
.\scripts\install_windows.ps1 -InstallProfile GUI

# 3. Create an empty test library.
conda run -n natureai-next natureai-next-admin library-create `
  D:\NatureAI-Next-Library --name "My Nature Library" --locale en

# 4. Verify the library.
conda run -n natureai-next natureai-next-admin library-check `
  D:\NatureAI-Next-Library --full

# 5. Start NatureAI Next.
.\scripts\start_windows.ps1 -Library D:\NatureAI-Next-Library
```

For local AI support, replace `GUI` with `FullAI` during installation.
NatureAI Legacy can remain installed; do not use its Conda environment or library.

## Validated RTX installation

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install_windows.ps1 -InstallProfile FullAI -TorchBuild CUDA124
```

## Uninstall

Keep the Conda environment but remove the application package:

```powershell
.\scripts\uninstall_windows.ps1
```

Remove the complete isolated environment:

```powershell
.\scripts\uninstall_windows.ps1 -RemoveEnvironment
```

Libraries and photographs are never deleted by these commands.

## Starting NatureAI Next after installation

Double-click **NatureAI Next** on the desktop or open it from the Start Menu. On first launch, select the initialized library folder. Later launches reopen the saved library automatically.

Use **NatureAI Next - Select Library** to change the saved library. Use **NatureAI Next (Debug)** when diagnostic console output is needed.

## Simplest full installation

After extracting the release, double-click `Install Aperture.cmd` in the release root. Enter the default Aperture library folder when prompted, or leave it blank and select a library later. Use `Repair Aperture.cmd` and `Uninstall Aperture.cmd` for their corresponding maintenance operations.


## Recommended interactive or unattended installation

Double-click `Install Aperture.cmd`. The installer asks for the storage drive rather than a technical library path. It explains that the Aperture Library contains the SQLite database, metadata, thumbnails, backups, and managed photographs and therefore grows over time. After a drive is selected, the installer creates `<drive>:\Aperture-Library` automatically or offers to reuse an existing valid Aperture Library.

Unattended examples:

```cmd
Install Aperture.cmd /silent /drive=D /profile=FullAI /useexisting
Install Aperture.cmd /silent /drive=D /profile=GUI /createnew
Install Aperture.cmd /silent /library="E:\Research\Aperture-Library" /profile=FullAI
```

Supported options include `/silent`, `/drive=`, `/profile=`, `/torch=`, `/library=`, `/useexisting`, `/createnew`, `/repair`, and `/skippreflight`.

## Python runtime bootstrap

A separate Python installation is not required. If Miniconda or Anaconda is not present, the Aperture installer downloads the official Miniconda Windows installer, verifies its published SHA-256 checksum, installs it for the current user, and then creates the isolated `natureai-next` Python 3.11 environment. For offline deployment, pass `-MinicondaInstallerPath` and optionally `-MinicondaSha256` to `scripts\install_windows.ps1`. Use `-SkipCondaBootstrap` only when deployment policy requires Conda to be installed separately.



### Conda channel isolation

The installer creates and maintains the Aperture environment with `--override-channels` and the `conda-forge` channel only. This avoids interactive Anaconda default-channel Terms of Service prompts during unattended installation.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.
