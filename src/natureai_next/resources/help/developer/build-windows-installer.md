# Build an Fieldora Windows installer

This build helper creates a native Windows Setup executable from the Fieldora source tree using:

- Miniconda / Conda
- Python 3.11
- PyInstaller
- Inno Setup 6

It creates `dist-installer\Fieldora-0.11.14-Setup.exe` and a matching SHA-256 file.

## Prerequisites

Install Miniconda and Inno Setup 6. In PowerShell:

```powershell
winget install --id JRSoftware.InnoSetup -e
```

Open a new PowerShell window after installation.

## Use

Copy `build_aperture_windows_installer.ps1` into the extracted Fieldora source root, next to `pyproject.toml`, then run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\build_aperture_windows_installer.ps1 `
  -BuildProfile GUI `
  -Version 0.11.14 `
  -Clean
```

For the much larger AI build:

```powershell
.\build_aperture_windows_installer.ps1 `
  -BuildProfile FullAI `
  -Version 0.11.14 `
  -Clean
```

The FullAI build includes Torch/OpenCLIP and requires substantially more time and storage. Test it on the target RTX/CUDA workstation.

## Output

```text
dist-installer\
├── Fieldora-0.11.14-Setup.exe
└── Fieldora-0.11.14-Setup.exe.sha256
```

## Important

This is a developer build pipeline, not a code-signing service. Before public distribution:

1. Test clean install, upgrade, repair, uninstall, backup, restore, and update on Windows 11.
2. Sign the Setup executable with an Authenticode certificate.
3. Verify the signed artifact and publish its final SHA-256.
4. Run antivirus and SmartScreen reputation checks.

An MSI requires a separate WiX Toolset project. For the current per-user desktop application, an Inno Setup EXE is the simpler first production installer.

# Recognizable Windows processes

The native installer build produces distinct frozen executables:

- `Fieldora.exe`
- `Fieldora.Maintenance.exe`
- `Fieldora.Manuals.exe`
- `Fieldora.Server.exe`
- `Fieldora.Worker.exe`
- `Fieldora.Updater.exe`
- `Fieldora.Recovery.exe`

Each executable embeds the Fieldora icon and Windows `CompanyName`,
`FileDescription`, `FileVersion`, `OriginalFilename`, `ProductName`, and
`ProductVersion` resources. Task Manager therefore shows the functional process
name instead of only `python.exe` or `pythonw.exe`.

The Python runtime is frozen by PyInstaller and is not renamed or copied under
an alias. This preserves Python and Conda runtime assumptions. The source-based
debug launcher remains available for diagnostic output.

Rerunning the same signed setup repairs or replaces the native application
directories. Inno Setup owns removal of the executables, shortcuts and install
directory. Fieldora libraries and the configured data root remain separate from
the program directory and are not removed by application uninstall.
