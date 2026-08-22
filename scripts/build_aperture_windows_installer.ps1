[CmdletBinding()]
param(
    [ValidateSet('GUI', 'FullAI')]
    [string]$BuildProfile = 'GUI',

    [string]$Version = '0.11.21',

    [string]$EnvironmentName = 'aperture-build',

    [string]$DefaultLibrary = '',

    [switch]$SkipTests,

    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw "Fieldora installer build failed: $Message"
}

function Resolve-Conda {
    $command = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:LOCALAPPDATA\miniconda3\Scripts\conda.exe",
        "$env:LOCALAPPDATA\anaconda3\Scripts\conda.exe",
        "C:\ProgramData\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    Fail 'Conda was not found. Install Miniconda and open a new PowerShell window.'
}

function Invoke-Conda([string[]]$Arguments) {
    & $script:Conda @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "conda command failed with exit code $LASTEXITCODE: conda $($Arguments -join ' ')"
    }
}

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '.')).Path
if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot 'pyproject.toml'))) {
    Fail 'Run this script from the extracted Fieldora repository root, next to pyproject.toml.'
}
if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot 'src\natureai_next'))) {
    Fail 'The src\natureai_next package was not found.'
}

$script:Conda = Resolve-Conda
$BuildRoot = Join-Path $RepositoryRoot '.installer-build'
$WrapperRoot = Join-Path $BuildRoot 'wrappers'
$PyInstallerWork = Join-Path $BuildRoot 'pyinstaller-work'
$PyInstallerSpec = Join-Path $BuildRoot 'pyinstaller-spec'
$ApplicationDist = Join-Path $BuildRoot 'application'
$InstallerDist = Join-Path $RepositoryRoot 'dist-installer'

if ($Clean) {
    Write-Step 'Cleaning previous build output'
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $InstallerDist -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $WrapperRoot, $PyInstallerWork, $PyInstallerSpec, $ApplicationDist, $InstallerDist | Out-Null

Write-Step "Creating or updating Conda build environment '$EnvironmentName'"
$environmentExists = (& $script:Conda env list --json | ConvertFrom-Json).envs | Where-Object { $_ -match "[\\/]$([regex]::Escape($EnvironmentName))$" }
if (-not $environmentExists) {
    Invoke-Conda @('create', '-y', '-n', $EnvironmentName, 'python=3.11', 'pip')
}

Write-Step 'Installing build dependencies and Fieldora'
Invoke-Conda @('run', '--no-capture-output', '-n', $EnvironmentName, 'python', '-m', 'pip', 'install', '--upgrade', 'pip', 'build', 'pyinstaller>=6.11,<7')
if ($BuildProfile -eq 'FullAI') {
    Invoke-Conda @('run', '--no-capture-output', '-n', $EnvironmentName, 'python', '-m', 'pip', 'install', '-e', '.[gui,ai]')
} else {
    Invoke-Conda @('run', '--no-capture-output', '-n', $EnvironmentName, 'python', '-m', 'pip', 'install', '-e', '.[gui]')
}

if (-not $SkipTests) {
    Write-Step 'Running practical automated tests'
    Invoke-Conda @('run', '--no-capture-output', '-n', $EnvironmentName, 'python', '-m', 'pip', 'install', '-e', '.[dev]')
    Invoke-Conda @('run', '--no-capture-output', '-n', $EnvironmentName, 'python', '-m', 'pytest', '-m', 'not performance')
}

$launcher = @'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from natureai_next.bootstrap.cli import main as aperture_main


def _settings_path() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home())) / "NatureAI" / "NatureAI Next"
    root.mkdir(parents=True, exist_ok=True)
    return root / "launcher.json"


def _valid_library(path: Path) -> bool:
    return path.is_dir() and (path / "library.json").is_file() and (path / "library.sqlite3").is_file()


def _saved_library() -> Path | None:
    try:
        value = json.loads(_settings_path().read_text(encoding="utf-8"))
        path = Path(str(value.get("last_library", "")))
        return path if _valid_library(path) else None
    except (OSError, ValueError, TypeError):
        return None


def _choose_library() -> Path | None:
    app = QApplication.instance() or QApplication([])
    while True:
        selected = QFileDialog.getExistingDirectory(None, "Select Fieldora Library")
        if not selected:
            return None
        path = Path(selected)
        if _valid_library(path):
            _settings_path().write_text(
                json.dumps({"schema_version": 1, "last_library": str(path)}, indent=2),
                encoding="utf-8",
            )
            return path
        QMessageBox.warning(
            None,
            "Fieldora",
            "Select the folder containing library.json and library.sqlite3.",
        )


def run() -> int:
    library = _saved_library() or _choose_library()
    if library is None:
        return 0
    return aperture_main(["--library", str(library), "--log-level", "INFO"])


if __name__ == "__main__":
    raise SystemExit(run())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'aperture_launcher.py') -Value $launcher -Encoding UTF8

$maintenanceLauncher = @'
from natureai_next.bootstrap.maintenance_center import main

if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'maintenance_launcher.py') -Value $maintenanceLauncher -Encoding UTF8

$manualsLauncher = @'
from natureai_next.bootstrap.manuals_app import main

if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'manuals_launcher.py') -Value $manualsLauncher -Encoding UTF8

$serverLauncher = @'
from natureai_next.bootstrap.server_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'server_launcher.py') -Value $serverLauncher -Encoding UTF8

# The worker intentionally shares the governed server command boundary. Invoke
# it with the run-job-worker command; the executable name remains recognizable.
Set-Content -LiteralPath (Join-Path $WrapperRoot 'worker_launcher.py') -Value $serverLauncher -Encoding UTF8

$updaterLauncher = @'
from natureai_next.bootstrap.native_updater import main

if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'updater_launcher.py') -Value $updaterLauncher -Encoding UTF8

$recoveryLauncher = @'
from natureai_next.bootstrap.native_recovery import main

if __name__ == "__main__":
    raise SystemExit(main())
'@
Set-Content -LiteralPath (Join-Path $WrapperRoot 'recovery_launcher.py') -Value $recoveryLauncher -Encoding UTF8

$icon = Join-Path $RepositoryRoot 'resources\fieldora.ico'
$recoveryIcon = Join-Path $RepositoryRoot 'resources\aperture-backup-recovery.ico'
$commonDataArgs = @(
    '--collect-all', 'natureai_next',
    '--collect-all', 'PySide6',
    '--hidden-import', 'PIL._tkinter_finder'
)
if ($BuildProfile -eq 'FullAI') {
    $commonDataArgs += @('--collect-all', 'torch', '--collect-all', 'torchvision', '--collect-all', 'open_clip')
}

function New-VersionFile(
    [string]$Name,
    [string]$Description,
    [string]$OriginalFilename
) {
    $numericVersion = ($Version -split '[^0-9]+' | Where-Object { $_ })[0..2]
    while ($numericVersion.Count -lt 4) { $numericVersion += '0' }
    $tuple = ($numericVersion[0..3] -join ', ')
    $path = Join-Path $WrapperRoot (($Name -replace '[^A-Za-z0-9.-]', '_') + '.version.txt')
    $content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($tuple),
    prodvers=($tuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Fieldora'),
         StringStruct('FileDescription', '$Description'),
         StringStruct('FileVersion', '$Version'),
         StringStruct('InternalName', '$Name'),
         StringStruct('LegalCopyright', 'Copyright Fieldora'),
         StringStruct('OriginalFilename', '$OriginalFilename'),
         StringStruct('ProductName', 'Fieldora Scientific Platform'),
         StringStruct('ProductVersion', '$Version')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
    return $path
}

function Build-App(
    [string]$Name,
    [string]$Wrapper,
    [string]$IconPath,
    [bool]$Windowed,
    [string]$Description
) {
    Write-Step "Building $Name"
    $versionFile = New-VersionFile -Name $Name -Description $Description -OriginalFilename "$Name.exe"
    $arguments = @(
        'run', '--no-capture-output', '-n', $EnvironmentName,
        'pyinstaller', '--noconfirm', '--clean', '--onedir',
        '--name', $Name,
        '--distpath', $ApplicationDist,
        '--workpath', $PyInstallerWork,
        '--specpath', $PyInstallerSpec,
        '--version-file', $versionFile,
        '--paths', (Join-Path $RepositoryRoot 'src')
    )
    if ($Windowed) { $arguments += '--windowed' }
    if (Test-Path -LiteralPath $IconPath) { $arguments += @('--icon', $IconPath) }
    $arguments += $commonDataArgs
    $arguments += $Wrapper
    Invoke-Conda $arguments
}

Build-App -Name 'Fieldora' -Wrapper (Join-Path $WrapperRoot 'aperture_launcher.py') -IconPath $icon -Windowed $true -Description 'Fieldora scientific desktop'
Build-App -Name 'Fieldora.Maintenance' -Wrapper (Join-Path $WrapperRoot 'maintenance_launcher.py') -IconPath $recoveryIcon -Windowed $true -Description 'Fieldora maintenance and recovery'
Build-App -Name 'Fieldora.Manuals' -Wrapper (Join-Path $WrapperRoot 'manuals_launcher.py') -IconPath $icon -Windowed $true -Description 'Fieldora offline manuals'
Build-App -Name 'Fieldora.Server' -Wrapper (Join-Path $WrapperRoot 'server_launcher.py') -IconPath $icon -Windowed $false -Description 'Fieldora server and API'
Build-App -Name 'Fieldora.Worker' -Wrapper (Join-Path $WrapperRoot 'worker_launcher.py') -IconPath $icon -Windowed $false -Description 'Fieldora background worker'
Build-App -Name 'Fieldora.Updater' -Wrapper (Join-Path $WrapperRoot 'updater_launcher.py') -IconPath $icon -Windowed $true -Description 'Fieldora updater'
Build-App -Name 'Fieldora.Recovery' -Wrapper (Join-Path $WrapperRoot 'recovery_launcher.py') -IconPath $recoveryIcon -Windowed $true -Description 'Fieldora recovery helper'

Write-Step 'Finding Inno Setup compiler'
$isccCandidates = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $Iscc) {
    Fail 'Inno Setup 6 was not found. Install it with: winget install --id JRSoftware.InnoSetup -e'
}

$defaultLibraryLine = if ($DefaultLibrary) { "DefaultLibrary=$DefaultLibrary" } else { 'DefaultLibrary=' }
$issPath = Join-Path $BuildRoot 'Fieldora.iss'
$iss = @"
#define MyAppName "Fieldora"
#define MyAppVersion "$Version"
#define MyAppPublisher "Fieldora"
#define MyAppExeName "Fieldora.exe"

[Setup]
AppId={{A99634D1-01DA-4C3B-B41E-E0FA44F23531}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Fieldora
DefaultGroupName=Fieldora
DisableProgramGroupPage=yes
OutputDir=$($InstallerDist.Replace('\','\\'))
OutputBaseFilename=Fieldora-$Version-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=$($icon.Replace('\','\\'))
UninstallDisplayIcon={app}\Fieldora\Fieldora.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora\*"; DestDir: "{app}\Fieldora"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Maintenance\*"; DestDir: "{app}\Maintenance"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Manuals\*"; DestDir: "{app}\Manuals"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Server\*"; DestDir: "{app}\Server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Worker\*"; DestDir: "{app}\Worker"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Updater\*"; DestDir: "{app}\Updater"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "$($ApplicationDist.Replace('\','\\'))\Fieldora.Recovery\*"; DestDir: "{app}\Recovery"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fieldora"; Filename: "{app}\Fieldora\Fieldora.exe"; IconFilename: "{app}\Fieldora\Fieldora.exe"
Name: "{group}\Fieldora Maintenance"; Filename: "{app}\Maintenance\Fieldora.Maintenance.exe"; IconFilename: "{app}\Maintenance\Fieldora.Maintenance.exe"
Name: "{group}\Fieldora Manuals"; Filename: "{app}\Manuals\Fieldora.Manuals.exe"; IconFilename: "{app}\Manuals\Fieldora.Manuals.exe"
Name: "{autodesktop}\Fieldora"; Filename: "{app}\Fieldora\Fieldora.exe"; Tasks: desktopicon
Name: "{autodesktop}\Fieldora Maintenance"; Filename: "{app}\Maintenance\Fieldora.Maintenance.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcuts"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\Fieldora\Fieldora.exe"; Description: "Launch Fieldora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
"@
Set-Content -LiteralPath $issPath -Value $iss -Encoding UTF8

Write-Step 'Compiling the Windows Setup executable'
& $Iscc $issPath
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed with exit code $LASTEXITCODE." }

$setupPath = Join-Path $InstallerDist "Fieldora-$Version-Setup.exe"
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
    Fail "Expected installer was not created: $setupPath"
}
$hash = (Get-FileHash -LiteralPath $setupPath -Algorithm SHA256).Hash.ToLowerInvariant()
$hashPath = "$setupPath.sha256"
"$hash  $(Split-Path -Leaf $setupPath)" | Set-Content -LiteralPath $hashPath -Encoding ASCII

Write-Step 'Build completed'
Write-Host "Installer: $setupPath"
Write-Host "SHA-256:   $hash"
Write-Host "Hash file: $hashPath"
Write-Warning 'This installer must be validated on Windows 11 before public distribution. FullAI builds can be very large and may require additional PyInstaller exclusions or hidden imports for the selected Torch/OpenCLIP versions.'
