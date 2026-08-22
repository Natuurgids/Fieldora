## Aperture V3.RC1F1 Full AI installation

Choose **Full AI** to install the BioCLIP model, CUDA/CPU variant, pybioclip runtime, TreeOfLifeClassifier, and Tree-of-Life resources. Setup primes and validates the classifier, then activates the NatureAI Tree-of-Life profile. On an upgrade, use Maintenance Center **Repair Full AI / NatureAI Engine**. GBIF and custom taxonomy CSV files are optional and are not required for initial NatureAI analysis.

# NatureAI Next — Windows 11 Source Installation

## Status

This procedure installs the current NatureAI Next source repository into an
isolated Miniconda environment. It is intended for controlled evaluation and
development. It is not yet the final signed Windows installer.

NatureAI Legacy may remain installed. NatureAI Next uses a separate Conda
environment and must use a separate library directory.

### Windows process names

The CMD installer keeps Python private to Aperture's managed environment. Maintenance Center, updater, and recovery use purpose-named runtime aliases. The primary desktop uses the package-generated Aperture GUI entry point because field validation found that a copied Python runtime with a friendly filename did not reliably launch on all tested Windows installations. Task Manager may therefore still expose `pythonw.exe` for the main CMD-installed application. Full primary-process branding belongs to the packaged executable installer and must not compromise startup reliability.

NatureAI is named separately only when AI execution runs in a separate process. Imports, thumbnails, indexing, matching, and repository enrichment are Aperture Background Services rather than NatureAI processes.

### Uninstall and running processes

Option 1 removes only the installed package and refuses while Aperture work is active. Options 2 and 3 remove the complete managed environment: they request graceful closure, wait for the applications to exit, and then stop remaining headless processes whose executable belongs to that environment. They never terminate Python processes installed elsewhere and never remove Aperture libraries, photographs, models, backups, or exports.

## 1. Prerequisites

Required:

- Windows 11 Pro, 64-bit
- Miniconda or Anaconda
- Internet access during dependency installation
- An extracted NatureAI Next repository containing `pyproject.toml`, `src`,
  `requirements`, `environment`, and `scripts`

Recommended for the FullAI profile:

- Current NVIDIA driver
- NVIDIA RTX 4070 Laptop GPU
- At least 20 GB free space for the environment, models, and temporary files

Docker Desktop is not required for this source installation.

## 2. What is reused and what stays isolated

The installer may reuse system-level components already used by NatureAI Legacy:

- NVIDIA driver
- Miniconda/Anaconda installation
- Visual C++ runtime
- Git and Docker Desktop

It does not install into the Legacy Conda environment and does not reuse the
Legacy database, settings, caches, plugins, or model registry.

The default environment name is:

```text
natureai-next
```

## 3. Extract the repository

Extract the ZIP to a stable path, for example:

```text
D:\Projects\NatureAI-Next
```

Do not run the scripts from the Windows ZIP preview.

Open PowerShell in the extracted repository:

```powershell
cd D:\Projects\NatureAI-Next
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

The execution-policy command applies only to the current PowerShell process.

## Automatic full installation when the extraction folder is unknown

Use this method for a **full installation** from the extracted release package when you are not sure which folder contains `scripts\install_windows.ps1`. It searches drive `D:` for the installer, changes to the release root, and starts the FullAI installation.

Close Aperture before running the installer. Open PowerShell and run:

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

## 4. Choose an installation profile

| Profile | Contents | Recommended use |
|---|---|---|
| `Core` | Core package and administrative CLI | Database/server-side checks without GUI |
| `GUI` | Core plus PySide6 | Recommended first installation |
| `FullAI` | GUI plus Torch, Torchvision, OpenCLIP and HNSWLib | RTX/CUDA and BioCLIP work |

`Full` is accepted as a compatibility alias for `FullAI`.

## 5. Recommended installation

Install the normal desktop profile:

```powershell
.\scripts\install_windows.ps1 -InstallProfile GUI
```

The script:

1. Finds the existing Miniconda or Anaconda installation.
2. Creates or reuses the isolated `natureai-next` environment.
3. Rejects an environment that is not using Python 3.11.
4. Installs the pinned profile dependencies from `requirements\`.
5. Installs NatureAI Next without sharing packages with Legacy.
6. Verifies the console entry points and selected optional modules.
7. Writes environment and package-inventory reports under `.installation\`.

Already compatible packages in the NatureAI Next environment are reused by pip.
The installer does not reinstall Miniconda and does not alter the Legacy
environment.

## 6. Full AI installation

On the target RTX machine:

```powershell
.\scripts\install_windows.ps1 -InstallProfile FullAI
```

This verifies that Torch imports and reports whether CUDA is available. A CUDA
`false` result does not damage the installation, but GPU inference will not be
available until the NVIDIA/Torch configuration is corrected.

## 7. Development installation

For editable source plus test and static-analysis tools:

```powershell
.\scripts\install_windows.ps1 `
  -InstallProfile GUI `
  -IncludeDevelopmentTools `
  -Editable
```

Run all configured repository validation after installation:

```powershell
.\scripts\install_windows.ps1 `
  -InstallProfile GUI `
  -IncludeDevelopmentTools `
  -Editable `
  -RunValidation
```

## 8. Existing environment handling

The installer reuses an existing environment named `natureai-next` only when it
uses Python 3.11.

Rebuild an uncertain or damaged environment:

```powershell
.\scripts\install_windows.ps1 `
  -InstallProfile GUI `
  -RecreateEnvironment
```

This removes only the named Conda environment. It does not remove repositories,
photo libraries, configuration directories, or model files.

Use a different environment name for testing:

```powershell
.\scripts\install_windows.ps1 `
  -EnvironmentName natureai-next-test `
  -InstallProfile GUI
```

## 9. Manual Conda installation alternative

The PowerShell installer is recommended. The checked-in environment files are
available for manual use:

```powershell
conda env create -f environment\environment-gui.yml
conda run -n natureai-next python scripts\verify_install.py --require-gui
```

Other definitions:

- `environment-core.yml`
- `environment-full.yml`
- `environment-dev.yml`

## 10. Verify the installation

GUI profile:

```powershell
conda run -n natureai-next python scripts\verify_install.py --require-gui
```

Full AI profile:

```powershell
conda run -n natureai-next python scripts\verify_install.py --require-gui --require-ai
```

The verifier is read-only and does not create or modify a library.

Installation reports:

```text
.installation\environment.txt
.installation\pip-freeze.txt
```

## 11. Create a first test library

Choose a new empty directory on a local SSD. Do not point NatureAI Next at a
NatureAI Legacy library.

```powershell
conda run -n natureai-next natureai-next-admin library-create `
  D:\NatureAI-Next-Library `
  --name "My Nature Library" `
  --locale en
```

Check it:

```powershell
conda run -n natureai-next natureai-next-admin library-check `
  D:\NatureAI-Next-Library `
  --full
```

## 12. Start the desktop application

```powershell
conda run -n natureai-next natureai-next `
  --library D:\NatureAI-Next-Library
```

Or use the wrapper:

```powershell
.\scripts\start_windows.ps1 -Library D:\NatureAI-Next-Library
```

Show all startup options:

```powershell
conda run -n natureai-next natureai-next --help
```

## 13. Administrative commands

```powershell
conda run -n natureai-next natureai-next-admin --help
```

The current repository includes commands for library creation and checks,
SQLite database backup, exports, and selected AI administration operations.
A SQLite-only backup is not yet a complete library disaster-recovery package.

## 14. Dependency files

The repository uses:

- `pyproject.toml` for supported dependency ranges and package metadata;
- `requirements\constraints-py311.txt` for selected direct-version pins;
- `requirements\core.txt`, `gui.txt`, `ai.txt`, and `dev.txt` for profiles;
- `environment\*.yml` for reproducible Conda environment creation.

The constraint file is deliberately separate from Legacy. It is not a fully
hash-locked transitive wheel bundle, so package downloads still require trusted
Conda/PyPI sources.

## 15. Troubleshooting

### Conda is not found

Open a new PowerShell window after installing Miniconda, or use “Miniconda
PowerShell Prompt.” The installer checks common installation paths.

### Existing environment uses the wrong Python

```powershell
.\scripts\install_windows.ps1 -InstallProfile GUI -RecreateEnvironment
```

### PySide6 fails to import

```powershell
conda run -n natureai-next python -c "from PySide6 import QtCore; print(QtCore.__version__)"
```

Re-run the GUI installer if this fails.

### Torch cannot see CUDA

```powershell
conda run -n natureai-next python -c `
  "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no CUDA device')"
```

Do not copy CUDA DLLs or Python packages from the Legacy environment.

### HNSWLib fails to install

Some Windows systems may require Microsoft C++ Build Tools when no compatible
prebuilt wheel is available. Install the “Desktop development with C++” workload,
open a new PowerShell window, and rerun the FullAI installation.

### Library is locked

Close every NatureAI Next process using the library. Do not delete lock files
while a process may still be active.

## 16. Updating this source installation

After replacing the repository with a newer verified snapshot, rerun the same
profile command. Compatible installed packages are reused and changed package
requirements are updated.

```powershell
.\scripts\install_windows.ps1 -InstallProfile GUI
```

For an editable development environment, keep using `-Editable`.

## 17. Uninstalling the source environment

```powershell
conda env remove -n natureai-next
```

This removes the Conda environment only. Remove the source repository,
configuration, model cache, and libraries separately and only after making any
required backups.

## 18. Current limitations

- The scripts are not code-signed.
- This is not the final packaged Windows installer.
- Full installation and validation must still be exercised on Windows 11 with
  Python 3.11.
- CUDA and BioCLIP behavior must be validated on the target RTX 4070 machine.
- Complete backup/restore and release packaging remain roadmap work.

## Validated baseline installer and uninstaller

The validated Windows baseline supports the RTX 4070 Laptop GPU with:

```powershell
.\scripts\install_windows.ps1 -InstallProfile FullAI -TorchBuild CUDA124
```

The installer deliberately installs HNSWLib through Conda Forge to avoid requiring Microsoft C++ Build Tools, then installs the official Torch 2.5.1 CUDA 12.4 wheels.

To uninstall only the NatureAI Next package while retaining the isolated environment:

```powershell
.\scripts\uninstall_windows.ps1
```

To remove the complete `natureai-next` Conda environment:

```powershell
.\scripts\uninstall_windows.ps1 -RemoveEnvironment
```

Neither operation removes NatureAI libraries, source photographs, backups, or exports. Application data is removed only when `-RemoveApplicationData` is supplied explicitly.

Before deleting old extracted source folders, preview them with:

```powershell
.\scripts\cleanup_old_builds.ps1
```

## Windows shortcuts and launchers (0.11.1)

The installer creates machine-local launcher files under:

```text
%LOCALAPPDATA%\NatureAI\NatureAI Next\Launchers
```

By default it creates desktop shortcuts for NatureAI Next, NatureAI Next (Debug), and NatureAI Next - Select Library. It also creates a NatureAI Next Start Menu folder containing those shortcuts and NatureAI Next Admin Console.

On the first normal launch, choose an initialized library folder containing `library.json` and `library.sqlite3`. The selected path is stored in:

```text
%APPDATA%\NatureAI\NatureAI Next\launcher.json
```

Use **NatureAI Next - Select Library** whenever the default library needs to change.

A library can be configured during installation:

```powershell
.\scripts\install_windows.ps1 `
  -InstallProfile FullAI `
  -TorchBuild CUDA124 `
  -DefaultLibrary D:\NatureAI-Libraries\TestLibrary
```

Shortcut creation can be disabled explicitly with `-CreateDesktopShortcuts:$false` or `-CreateStartMenuShortcuts:$false`.

## Windows Installed Apps registration (0.11.2)

The installer registers NatureAI Next for the current Windows user. After installation it should appear under **Settings → Apps → Installed apps** with version, publisher, repair, and uninstall information. No administrator rights are required.

To repair shortcuts and registration without reinstalling dependencies:

```powershell
.\scripts\repair_windows_integration.ps1 `
  -DefaultLibrary D:\NatureAI-Libraries\TestLibrary
```

The Start Menu also contains **Repair NatureAI Next** and **Uninstall NatureAI Next** entries.


## Local AI resource packaging

After installing the FullAI profile, run `natureai-next-resources --help`. Templates and the complete workflow are in `resources/README.md`. Model weights and taxonomy data are not bundled and must be obtained under their upstream licenses.

## Command-line PATH integration

The Windows installer adds the active NatureAI Conda environment and its `Scripts` directory to the current user's PATH. Open a new PowerShell or Command Prompt after installation. The uninstaller removes only those exact entries. Set `-AddEnvironmentToUserPath:$false` to opt out.

## One-click CMD launchers

The Version 1.0 release root includes user-facing Windows launchers:

- `Install Aperture.cmd` — full FullAI/CUDA124 installation;
- `Repair Aperture.cmd` — repairs shortcuts, PATH integration, and Windows registration;
- `Uninstall Aperture.cmd` — removes the package or environment without deleting libraries or photographs.

For the normal installation, extract the ZIP and double-click `Install Aperture.cmd`. The launcher runs the existing PowerShell installer with a process-scoped execution-policy bypass, keeps the window open on failure, and optionally records a default library path. Advanced users may continue to call `scripts\install_windows.ps1` directly.


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

## Maintenance Center library selection

The installer records the selected Aperture Library in the shared launcher configuration. Maintenance Center normally opens that library automatically. If the configuration is missing, unreadable, or points to an unavailable library, Maintenance Center asks the user to select a valid Aperture Library folder rather than requiring command-line arguments.

## Regional taxonomy installation

The existing Regional Knowledge **Save & Install** operation installs the verified GBIF regional taxonomy into both the BioCLIP regional resources and the shared Taxonomy Reference database. The Knowledge Center therefore uses the same downloaded Latin names, common names where supplied, ranks, authorship, and regional occurrence records without a separate download.


## Build 3.321 RC3 update

GBIF Darwin Core taxonomy import is separate from model installation; offline PMTiles use a glyph-independent local street style; and BioCLIP downloads resume from persistent partial files after remote disconnects.
