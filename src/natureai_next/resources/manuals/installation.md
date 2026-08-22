| **Release**  | 0.11.21 — AI review and offline map labels              |
|--------------|----------------------------------------------------------------------------|
| **Audience** | Desktop installers, local IT support, evaluators, and deployment engineers |
| **Platform** | Windows 11 desktop; optional multi-server deployment                       |
| **Status**   | Operational reference — July 2026                                          |

**This manual reflects the packaged Fieldora 5.4.0 source release.
Commands that change data should first be exercised against a test
library or non-production environment.**

The document OCR provider is installed from the Models workspace. It uses an
isolated PyMuPDF, NumPy, and RapidOCR ONNX dependency directory and does not
require a separately installed Tesseract executable. Installation may require
network access; verified OCR execution is offline afterward.

# How to use this manual

Follow procedures in order. Text marked Important identifies a safety or
security boundary. Command blocks are intended to be copied only after
paths, environment names, and organization identifiers are replaced.

# Contents

- 1\. Scope and supported installation models

- 2\. Prerequisites and sizing

- 3\. Release acquisition and integrity

- 4\. Windows interactive installation

- 5\. PowerShell installation

- 6\. Profiles: Core, GUI, FullAI

- 7\. First library and first launch

- 8\. Full AI and GPU validation

- 9\. Offline and controlled-network installation

- 10\. Upgrade and rollback

- 11\. Repair and recovery

- 12\. Uninstallation

- 13\. Troubleshooting

- 14\. Installation acceptance checklist

# 1. Scope and supported installation models

Fieldora can run as a local Windows desktop application, as a core
command-line installation, or as a desktop connected to separately
operated server services. The normal research workstation begins with
the GUI profile. FullAI adds local model execution and substantially
larger dependencies.

| **Model**           | **Use**                                                     | **Data location**                      |
|---------------------|-------------------------------------------------------------|----------------------------------------|
| Core                | Administration, validation, and server-side commands        | Explicit data root or library path     |
| GUI                 | Normal desktop research and library management              | Local Fieldora library                 |
| FullAI              | GUI plus local BioCLIP and related AI resources             | Library plus model/resource roots      |
| Production services | Multi-node API, workers, PostgreSQL, object storage, search | Externally managed production services |

**Important:** Do not point Fieldora at a NatureAI Legacy or unrelated
Fieldora library. Use a separate library and retain the original data
unchanged.

# 2. Prerequisites and sizing

- Windows 11 Pro 64-bit and permission to create a per-user Conda
  environment.

- Python 3.11 inside the managed environment; newer or older Python
  versions are rejected.

- A stable extraction folder containing pyproject.toml, src,
  requirements, environment, and scripts.

- Internet access for normal dependency installation, or a fully
  prepared offline dependency source.

- GUI: at least 8 GB RAM and several GB of free disk space. FullAI: 20
  GB or more is recommended.

- For CUDA execution: a supported NVIDIA driver and a Torch build
  matching the selected installer option.

- A new library directory on a local SSD. Avoid network shares for
  SQLite-backed standalone libraries.

## Pre-installation checklist

1.  Close all Fieldora, Fieldora, worker, updater, and maintenance
    processes.

2.  Back up any existing Fieldora library and verify the backup.

3.  Confirm the target release shows version 0.10.11 in VERSION and
    PLATFORM_RELEASE.json.

4.  Choose the environment name, installation profile, storage drive,
    and library path.

5.  Ensure security software permits the installer, Python environment,
    and Qt WebEngine runtime.

# 3. Release acquisition and integrity

Extract the release ZIP completely. Do not execute scripts from the
Windows ZIP preview. Preserve the package layout because requirements,
resources, Excalidraw assets, and helper scripts use relative paths.

Get-FileHash .\Fieldora-0.10.11-excalidraw-startup-hotfix.zip -Algorithm
SHA256

Compare the result with the digest supplied through your approved
release channel. After extraction, retain RELEASE_MANIFEST.json with the
release. Deployment preflight and recovery processes use packaged
manifests as an integrity boundary.

# 4. Windows interactive installation

6.  Right-click the ZIP and select Extract All.

7.  Open the extracted root, not a nested preview.

8.  Double-click Install Fieldora.cmd. The compatibility filename is
    retained, while installed links use the Fieldora identity.

9.  Choose GUI for a normal workstation or FullAI for local inference.

10. Choose a storage drive or explicit library path. For a first
    installation, create a new library.

11. Allow dependency installation and verification to finish.

12. Launch Fieldora from the installed shortcut and confirm About
    reports 0.10.11.

Install Fieldora.cmd /silent /drive=D /profile=GUI /createnew

Install Fieldora.cmd /silent /library="E:\Research\Fieldora-Library"
/profile=FullAI

**Important:** Silent installation must explicitly select whether to
create or reuse a library. Never automate reuse of a directory that has
not passed library-check.

# 5. PowerShell installation

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\scripts\install_windows.ps1 -InstallProfile GUI

.\scripts\install_windows.ps1 -InstallProfile FullAI -TorchBuild CUDA124

The installer locates Miniconda or Anaconda, or bootstraps Miniconda
where allowed; creates or reuses the isolated natureai-next environment;
enforces Python 3.11; installs pinned dependencies; installs Fieldora;
verifies selected modules and entry points; and writes package reports
beneath .installation.

## Controlled variations

.\scripts\install_windows.ps1 -EnvironmentName fieldora-test
-InstallProfile GUI

.\scripts\install_windows.ps1 -InstallProfile GUI -RecreateEnvironment

.\scripts\install_windows.ps1 -InstallProfile GUI
-IncludeDevelopmentTools -Editable -RunValidation

# 6. Profiles: Core, GUI, FullAI

| **Profile** | **Includes**                                                     | **Choose when**                |
|-------------|------------------------------------------------------------------|--------------------------------|
| Core        | Core package and administrative CLI                              | No desktop UI is needed        |
| GUI         | Core plus PySide6, Qt Multimedia, and Qt WebEngine               | Normal desktop use             |
| FullAI      | GUI plus Torch, Torchvision, OpenCLIP, HNSWLib, and AI resources | Local AI inference is required |

The FFmpeg message printed by Qt Multimedia is informational. A Python
traceback is not informational: use the first exception near the bottom
to identify the primary failure.

# 7. First library and first launch

conda run -n natureai-next natureai-next-admin library-create
D:\Fieldora-Library --name "Research Library" --locale en

conda run -n natureai-next natureai-next-admin library-check
D:\Fieldora-Library --full

conda run -n natureai-next natureai-next --library D:\Fieldora-Library

- Confirm the splash and About page identify Fieldora 0.10.11.

- Open Library and verify the photo workspace loads.

- Open Science \> Excalidraw Whiteboards. Drawing 1 should appear
  embedded without a separate Excalidraw installation.

- Run a filename and directory-name search.

- Import a small copy of test media before using production data.

# 8. Full AI and GPU validation

conda run -n natureai-next python scripts\verify_install.py
--require-gui --require-ai

- Check that Torch imports successfully.

- Check whether CUDA is reported as available.

- Open AI Resources and verify the selected model, execution variant,
  classifier, and taxonomy resources.

- Do not activate an empty prompt set or incomplete inference path.

- Treat GBIF import as optional enrichment, not a prerequisite for
  BioCLIP installation.

# 9. Offline and controlled-network installation

For disconnected deployment, pre-stage the release, Conda installer,
package caches, AI model files, taxonomy resources, and checksums
through an approved transfer process. Use the PowerShell installer's
offline Miniconda options when provided. Do not disable certificate
validation or embed repository credentials in scripts.

- Record hashes for every transferred installer and model package.

- Keep secrets and DSN files outside the extracted release and library.

- Block network access for the embedded Excalidraw editor; its assets
  are bundled.

- Validate the completed environment with verify_install.py before
  introducing research data.

# 10. Upgrade and rollback

13. Back up and verify the active library.

14. Close desktop and background processes.

15. Retain the prior release archive and environment inventory.

16. Extract the new package to a separate stable folder.

17. Run the installer or repair path against the existing isolated
    environment.

18. Run library-check and start the application.

19. Verify the release number, Excalidraw, search, import, thumbnails,
    AI resources, and exports.

20. Keep the rollback package until acceptance is signed off.

**Important:** Do not downgrade a library after irreversible schema
changes unless the release documentation explicitly supports it. Restore
a verified pre-upgrade backup instead.

# 11. Repair and recovery

Repair Fieldora.cmd

.\scripts\install_windows.ps1 -InstallProfile GUI -RecreateEnvironment

Use package repair for missing dependencies or entry points. Recreate
the environment when Python, Qt, or compiled packages are inconsistent.
Environment recreation does not authorize deletion of libraries,
photographs, models, exports, or backups.

# 12. Uninstallation

.\scripts\uninstall_windows.ps1

.\scripts\uninstall_windows.ps1 -RemoveEnvironment

- Close running Fieldora processes before uninstall.

- Normal uninstall removes the package but may retain the isolated
  environment.

- RemoveEnvironment removes only the named managed Conda environment.

- Current Fieldora and compatibility launcher links should be removed.

- Libraries, photographs, models, backups, and exports are not deleted.
  Verify those locations manually before any separate cleanup.

# 13. Troubleshooting

| **Symptom**                                   | **Likely cause**                              | **Action**                                                                       |
|-----------------------------------------------|-----------------------------------------------|----------------------------------------------------------------------------------|
| QListWidgetItem NameError                     | Pre-0.10.11 Excalidraw startup defect         | Install 0.10.11 or later; verify About version                                   |
| WebEnginePage/profile warning after traceback | Secondary cleanup after constructor crash     | Fix the preceding Python exception first                                         |
| MigrationError: exact schema required         | Library/release mismatch                      | Use Debug diagnostics; do not force migration; restore or use compatible release |
| CUDA unavailable                              | Driver/Torch mismatch or CPU build            | Run verify_install; inspect NVIDIA driver and selected Torch build               |
| Shortcut remains after uninstall              | Old compatibility link or interrupted removal | Rerun current uninstaller with apps closed; inspect Start Menu/Desktop links     |
| Library stalls while scrolling                | Old thumbnail scheduling behavior             | Confirm current release; thumbnails should wait until scrolling is idle          |

## Diagnostic capture

conda run -n natureai-next natureai-next --library D:\Fieldora-Library

Capture the complete traceback, release version, selected library path,
installation profile, Windows version, and whether the problem occurs
with a new empty test library. Never include passwords, access tokens,
private DSNs, or sensitive research metadata.

# 14. Installation acceptance checklist

- Release files and manifest verified.

- Correct profile installed in an isolated Python 3.11 environment.

- verify_install passes for the selected profile.

- New or approved library passes library-check --full.

- Desktop starts without traceback.

- Photo browsing, idle thumbnail loading, filename/path search, and
  import work.

- Embedded Excalidraw opens Drawing 1 inside Fieldora.

- Backup and restore procedure documented.

- Uninstall and rollback path understood.

- Acceptance record includes release digest and operator.
