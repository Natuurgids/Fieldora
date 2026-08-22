[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$EnvironmentName = 'fieldora-v5',

    [ValidateSet('Core', 'GUI', 'Full', 'FullAI')]
    [string]$InstallProfile = 'FullAI',

    [ValidateSet('CUDA124', 'CPU')]
    [string]$TorchBuild = 'CUDA124',

    [switch]$IncludeDevelopmentTools,
    [switch]$Editable,
    [switch]$RecreateEnvironment,
    [switch]$RunValidation,
    [switch]$SkipSmokeTest,
    [switch]$SkipDependencyInstallation,
    [switch]$SkipPackageInstallation,
    [switch]$SkipDeploymentPreflight,
    [switch]$SkipCondaBootstrap,
    [string]$MinicondaInstallerPath,
    [string]$MinicondaSha256,

    [string]$DefaultLibrary,
    [bool]$CreateDefaultLibrary = $false,
    [string]$DataRoot,
    [bool]$CreateDesktopShortcuts = $true,
    [bool]$CreateStartMenuShortcuts = $true,
    [bool]$AddEnvironmentToUserPath = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Build 26 Repair 8 treats installation as clean by default.
if (-not $PSBoundParameters.ContainsKey('RecreateEnvironment')) { $RecreateEnvironment = $true }

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([Parameter(Mandatory)][string]$Message)
    throw "NatureAI Next installation failed: $Message"
}

function Resolve-CondaExecutable {
    foreach ($name in @('conda.exe', 'conda')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command -and $command.CommandType -eq 'Application') {
            return $command.Source
        }
    }

    $candidates = @(
        (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'),
        (Join-Path $env:LOCALAPPDATA 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:LOCALAPPDATA 'anaconda3\Scripts\conda.exe'),
        'C:\ProgramData\miniconda3\Scripts\conda.exe',
        'C:\ProgramData\anaconda3\Scripts\conda.exe'
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Install-MinicondaBootstrap {
    if ($SkipCondaBootstrap) {
        Fail 'Miniconda or Anaconda was not found. Install Miniconda first or rerun without -SkipCondaBootstrap.'
    }

    Write-Step 'Installing the Aperture Python runtime (Miniconda)'
    $targetDirectory = Join-Path $script:DataRoot 'runtime\miniconda3'
    $installer = $MinicondaInstallerPath
    $downloadedInstaller = $false
    if (-not $installer) {
        $installerName = 'Miniconda3-latest-Windows-x86_64.exe'
        $installer = Join-Path $env:TEMP $installerName
        $repositoryUrl = 'https://repo.anaconda.com/miniconda/'
        $installerUrl = $repositoryUrl + $installerName
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $installerUrl -OutFile $installer
            $downloadedInstaller = $true
            if (-not $MinicondaSha256) {
                # The Miniconda repository publishes SHA-256 values in its directory index.
                # A .sha256 sidecar is not guaranteed to exist, so parse the authoritative
                # index instead of treating a missing sidecar as a failed installer download.
                $indexResponse = Invoke-WebRequest -UseBasicParsing -Uri $repositoryUrl
                $escapedName = [regex]::Escape($installerName)
                $pattern = $escapedName + '.*?([0-9a-fA-F]{64})'
                $match = [regex]::Match($indexResponse.Content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
                if (-not $match.Success) {
                    Fail 'Miniconda was downloaded, but its published SHA-256 could not be read from the official repository index.'
                }
                $MinicondaSha256 = $match.Groups[1].Value.ToLowerInvariant()
            }
        }
        catch {
            Fail ("Miniconda could not be downloaded or verified. Provide an offline installer with -MinicondaInstallerPath. {0}" -f $_.Exception.Message)
        }
    }
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        Fail "Miniconda installer was not found: $installer"
    }
    if ($MinicondaSha256) {
        $actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $MinicondaSha256.ToLowerInvariant()) {
            Fail 'The Miniconda installer checksum did not match.'
        }
    }
    else {
        Write-Warning 'No Miniconda checksum was supplied for the offline installer.'
    }

    $arguments = @('/InstallationType=JustMe', '/RegisterPython=0', '/AddToPath=0', '/S', "/D=$targetDirectory")
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        Fail "Miniconda installation failed with exit code $($process.ExitCode)."
    }
    $conda = Join-Path $targetDirectory 'Scripts\conda.exe'
    if (-not (Test-Path -LiteralPath $conda -PathType Leaf)) {
        Fail 'Miniconda completed but conda.exe was not found.'
    }
    if ($downloadedInstaller) {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath ($installer + '.sha256') -Force -ErrorAction SilentlyContinue
    }
    return $conda
}

function Ensure-CondaExecutable {
    $conda = Resolve-CondaExecutable
    if ($null -eq $conda) {
        $conda = Install-MinicondaBootstrap
    }
    return $conda
}

function Invoke-Conda {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & $script:CondaExecutable @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail ("conda command failed with exit code {0}: conda {1}" -f $LASTEXITCODE, ($Arguments -join ' '))
    }
}

function Invoke-InEnvironment {
    param([Parameter(Mandatory)][string[]]$Arguments)
    Invoke-Conda -Arguments (@('run', '--no-capture-output', '-n', $EnvironmentName) + $Arguments)
}

function Get-EnvironmentRecord {
    $json = & $script:CondaExecutable env list --json
    if ($LASTEXITCODE -ne 0) {
        Fail 'Unable to query Conda environments.'
    }
    $data = $json | ConvertFrom-Json
    foreach ($path in @($data.envs)) {
        if ((Split-Path -Leaf $path) -eq $EnvironmentName) {
            return $path
        }
    }
    return $null
}


function Add-NatureAIUserPath {
    param([Parameter(Mandatory)][string]$EnvironmentPath)

    $required = @(
        (Join-Path $EnvironmentPath 'Scripts'),
        $EnvironmentPath
    )
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($userPath) {
        $entries = @($userPath -split ';' | Where-Object { $_ -and $_.Trim() })
    }
    foreach ($path in $required) {
        $normalized = [System.IO.Path]::GetFullPath($path).TrimEnd('\')
        $exists = $false
        foreach ($entry in $entries) {
            try {
                if ([System.IO.Path]::GetFullPath($entry).TrimEnd('\').Equals($normalized, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $exists = $true
                    break
                }
            } catch { }
        }
        if (-not $exists) { $entries += $normalized }
        if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\').Equals($normalized, [System.StringComparison]::OrdinalIgnoreCase) })) {
            $env:Path = "$normalized;$env:Path"
        }
    }
    [Environment]::SetEnvironmentVariable('Path', ($entries -join ';'), 'User')
    Write-Host "User PATH includes: $($required -join ', ')"
    Write-Host 'Open a new PowerShell window before using NatureAI commands by name.'
}

function New-WindowsShortcut {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$TargetPath,
        [string]$Arguments = '',
        [string]$WorkingDirectory = '',
        [string]$Description = '',
        [string]$IconLocation = ''
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    if ($WorkingDirectory) { $shortcut.WorkingDirectory = $WorkingDirectory }
    if ($Description) { $shortcut.Description = $Description }
    if ($IconLocation) { $shortcut.IconLocation = $IconLocation }
    $shortcut.Save()
}

function Install-FriendlyRuntimeAliases {
    param([Parameter(Mandatory)][string]$EnvironmentPath)

    $source = Join-Path $EnvironmentPath 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        $source = Join-Path $EnvironmentPath 'python.exe'
    }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        Fail "The Python runtime was not found in $EnvironmentPath."
    }

    # Build 3 field validation found that a copied Python runtime is not a
    # reliable primary GUI launcher on every Windows installation. Remove the
    # obsolete alias and keep the proven generated GUI entry point instead.
    Remove-Item -LiteralPath (Join-Path $EnvironmentPath 'Aperture.exe') -Force -ErrorAction SilentlyContinue

    # Console/gui entry points generated by packaging are the authoritative
    # launchers. Copying pythonw.exe under friendly names is unreliable because
    # Python startup semantics depend on the executable name and location.
}


function Register-WindowsApplication {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$EnvironmentPath,
        [Parameter(Mandatory)][string]$LauncherRoot,
        [Parameter(Mandatory)][string]$DataRoot,
        [Parameter(Mandatory)][string]$Version
    )

    $desktopExecutable = Join-Path $EnvironmentPath 'Scripts\natureai-next.exe'
    $apertureIcon = Join-Path $RepositoryRoot 'resources\fieldora.ico'
    $displayIcon = if (Test-Path -LiteralPath $apertureIcon -PathType Leaf) { $apertureIcon } else { $desktopExecutable }
    $registrationRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Fieldora V5'
    $installedUninstaller = Join-Path $LauncherRoot 'uninstall_windows.ps1'
    $repairScript = Join-Path $LauncherRoot 'repair_shortcuts.ps1'
    $sourceUninstaller = Join-Path $RepositoryRoot 'scripts\uninstall_windows.ps1'

    Copy-Item -LiteralPath $sourceUninstaller -Destination $installedUninstaller -Force

    $repairContent = @'
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installScript = '__INSTALL_SCRIPT__'
$environmentName = '__ENVIRONMENT_NAME__'
$dataRoot = '__DATA_ROOT__'
if (-not (Test-Path -LiteralPath $installScript -PathType Leaf)) {
    throw "The NatureAI Next release folder is unavailable: $installScript"
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installScript `
    -EnvironmentName $environmentName `
    -DataRoot $dataRoot `
    -InstallProfile Core `
    -RecreateEnvironment:$false `
    -SkipDependencyInstallation `
    -SkipPackageInstallation `
    -SkipSmokeTest
exit $LASTEXITCODE
'@
    $repairContent = $repairContent.Replace('__INSTALL_SCRIPT__', (Join-Path $RepositoryRoot 'scripts\install_windows.ps1').Replace("'", "''"))
    $repairContent = $repairContent.Replace('__ENVIRONMENT_NAME__', $EnvironmentName.Replace("'", "''"))
    $repairContent = $repairContent.Replace('__DATA_ROOT__', $DataRoot.Replace("'", "''"))
    Set-Content -LiteralPath $repairScript -Value $repairContent -Encoding UTF8

    $powerShellExecutable = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powerShellExecutable -PathType Leaf)) { $powerShellExecutable = 'powershell.exe' }
    $uninstallCommand = '"{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}" -EnvironmentName "{2}" -InstallationRoot "{3}"' -f $powerShellExecutable, $installedUninstaller, $EnvironmentName, $RepositoryRoot
    $quietUninstallCommand = $uninstallCommand + ' -Confirm:$false'
    $modifyCommand = '"{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}"' -f $powerShellExecutable, $repairScript

    New-Item -Path $registrationRoot -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'DisplayName' -Value 'Fieldora V5' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'DisplayVersion' -Value $Version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'Publisher' -Value 'natuurgids.org' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'InstallLocation' -Value $RepositoryRoot -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'DisplayIcon' -Value "$displayIcon,0" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'UninstallString' -Value $uninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'QuietUninstallString' -Value $quietUninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'ModifyPath' -Value $modifyCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'NoModify' -Value 0 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'NoRepair' -Value 0 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'EstimatedSize' -Value 0 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'InstallDate' -Value (Get-Date -Format 'yyyyMMdd') -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $registrationRoot -Name 'WindowsInstaller' -Value 0 -PropertyType DWord -Force | Out-Null

    $startMenuDirectory = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Fieldora V5'
    New-Item -ItemType Directory -Force -Path $startMenuDirectory | Out-Null
    New-WindowsShortcut `
        -Path (Join-Path $startMenuDirectory 'Repair Fieldora V5.lnk') `
        -TargetPath $powerShellExecutable `
        -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$repairScript`"" `
        -WorkingDirectory $LauncherRoot `
        -Description 'Repair Fieldora Windows shortcuts and registration' `
        -IconLocation "$displayIcon,0"
    New-WindowsShortcut `
        -Path (Join-Path $startMenuDirectory 'Uninstall Fieldora V5.lnk') `
        -TargetPath $powerShellExecutable `
        -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$installedUninstaller`" -EnvironmentName `"$EnvironmentName`" -InstallationRoot `"$RepositoryRoot`"" `
        -WorkingDirectory $LauncherRoot `
        -Description 'Uninstall Fieldora' `
        -IconLocation "$displayIcon,0"

    Write-Host "Registered application: $registrationRoot"
}

# Legacy shortcut labels retained for upgrade/uninstall compatibility: NatureAI Next - Select Library; Repair NatureAI Next; Uninstall NatureAI Next
function Install-WindowsLaunchers {
    param(
        [Parameter(Mandatory)][string]$EnvironmentPath,
        [Parameter(Mandatory)][string]$DataRoot,
        [string]$InitialLibrary,
        [bool]$DesktopShortcuts,
        [bool]$StartMenuShortcuts
    )

    $launcherRoot = Join-Path $DataRoot 'launchers'
    $configurationRoot = Join-Path $DataRoot 'roaming'
    New-Item -ItemType Directory -Force -Path $launcherRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $configurationRoot | Out-Null

    Install-FriendlyRuntimeAliases -EnvironmentPath $EnvironmentPath

    $desktopExecutable = Join-Path $EnvironmentPath 'Scripts\natureai-next.exe'
    $apertureIcon = Join-Path $RepositoryRoot 'resources\fieldora.ico'
    $displayIcon = if (Test-Path -LiteralPath $apertureIcon -PathType Leaf) { $apertureIcon } else { $desktopExecutable }
    $adminExecutable = Join-Path $EnvironmentPath 'Scripts\natureai-next-admin.exe'
    $maintenanceExecutable = Join-Path $EnvironmentPath 'Scripts\fieldora-maintenance-center.exe'
    if (-not (Test-Path -LiteralPath $desktopExecutable -PathType Leaf)) {
        Fail "Desktop executable was not found at $desktopExecutable."
    }
    if (-not (Test-Path -LiteralPath $adminExecutable -PathType Leaf)) {
        Fail "Administrative executable was not found at $adminExecutable."
    }
    if (-not (Test-Path -LiteralPath $maintenanceExecutable -PathType Leaf)) {
        Fail "Maintenance Center executable was not found at $maintenanceExecutable."
    }

    $commonPath = Join-Path $launcherRoot 'launcher_common.ps1'
    $commonScript = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:APERTURE_DATA_ROOT = '__DATA_ROOT__'
$env:NATUREAI_DATA_ROOT = $env:APERTURE_DATA_ROOT
$env:HF_HOME = Join-Path $env:APERTURE_DATA_ROOT 'cache\huggingface'
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:TORCH_HOME = Join-Path $env:APERTURE_DATA_ROOT 'cache\torch'
$env:XDG_CACHE_HOME = Join-Path $env:APERTURE_DATA_ROOT 'cache'
$script:LauncherConfigurationRoot = Join-Path $env:APERTURE_DATA_ROOT 'roaming'
$script:LauncherConfigurationPath = Join-Path $script:LauncherConfigurationRoot 'launcher.json'
$script:ApertureAdminExecutable = '__ADMIN_EXECUTABLE__'

function Test-NatureAILibrary {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    return (
        (Test-Path -LiteralPath (Join-Path $Path 'library.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $Path 'library.sqlite3') -PathType Leaf)
    )
}

function Test-EmptyLibraryDirectory {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    return -not [bool](Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1)
}

function Assert-SeparateLibraryRoot {
    param([Parameter(Mandatory)][string]$Path)
    $library = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $data = [System.IO.Path]::GetFullPath($env:APERTURE_DATA_ROOT).TrimEnd('\')
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    if ($library.Equals($data, $comparison) -or
        $library.StartsWith($data + '\', $comparison) -or
        $data.StartsWith($library + '\', $comparison)) {
        throw "The Aperture library and FieldoraData-V5 must be separate, non-nested directories.`nLibrary: $library`nApplication data: $data"
    }
}

function Initialize-NatureAILibrary {
    param([Parameter(Mandatory)][string]$Path)
    Assert-SeparateLibraryRoot -Path $Path
    if (-not (Test-EmptyLibraryDirectory -Path $Path)) {
        throw "The selected folder is not empty: $Path"
    }
    & $script:ApertureAdminExecutable library-create $Path --name 'Aperture Library' --locale en
    if ($LASTEXITCODE -ne 0 -or -not (Test-NatureAILibrary -Path $Path)) {
        throw "Aperture could not initialize the selected library folder: $Path"
    }
}

function Save-NatureAILibrary {
    param([Parameter(Mandatory)][string]$Path)
    Assert-SeparateLibraryRoot -Path $Path
    if (-not (Test-NatureAILibrary -Path $Path)) {
        throw "Not a valid NatureAI Next library: $Path"
    }
    New-Item -ItemType Directory -Force -Path $script:LauncherConfigurationRoot | Out-Null
    $temporaryPath = "$script:LauncherConfigurationPath.tmp"
    @{ schema_version = 2; release_line = '4.0'; last_library = (Resolve-Path -LiteralPath $Path).Path } |
        ConvertTo-Json |
        Set-Content -LiteralPath $temporaryPath -Encoding UTF8
    Move-Item -LiteralPath $temporaryPath -Destination $script:LauncherConfigurationPath -Force
}

function Read-NatureAILibrary {
    if (-not (Test-Path -LiteralPath $script:LauncherConfigurationPath -PathType Leaf)) { return $null }
    try {
        $value = Get-Content -LiteralPath $script:LauncherConfigurationPath -Raw | ConvertFrom-Json
        $schemaVersion = [int]$value.schema_version
        $releaseLine = [string]$value.release_line
        $path = [string]$value.last_library
        if ($schemaVersion -eq 2 -and $releaseLine -eq '4.0' -and $path -and (Test-NatureAILibrary -Path $path)) { return $path }
    }
    catch { return $null }
    return $null
}

function Select-NatureAILibrary {
    Add-Type -AssemblyName System.Windows.Forms
    while ($true) {
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Select an Aperture library. Empty folders are initialized atomically. Existing libraries are opened without migration, cleanup, or replacement.'
        $dialog.ShowNewFolderButton = $true
        $result = $dialog.ShowDialog()
        if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return $null }
        $selected = $dialog.SelectedPath
        if (Test-NatureAILibrary -Path $selected) {
            Save-NatureAILibrary -Path $selected
            return $selected
        }
        if (Test-EmptyLibraryDirectory -Path $selected) {
            $answer = [System.Windows.Forms.MessageBox]::Show(
                "Create a new Aperture V4 library in this folder?`n`n$selected",
                'Aperture',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Question
            )
            if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) {
                try {
                    Initialize-NatureAILibrary -Path $selected
                    Save-NatureAILibrary -Path $selected
                    return $selected
                }
                catch {
                    [System.Windows.Forms.MessageBox]::Show(
                        $_.Exception.Message,
                        'Aperture',
                        [System.Windows.Forms.MessageBoxButtons]::OK,
                        [System.Windows.Forms.MessageBoxIcon]::Error
                    ) | Out-Null
                }
            }
            continue
        }
        [System.Windows.Forms.MessageBox]::Show(
            'The selected folder is neither an Aperture library nor empty. Unrelated files are protected and were not changed.',
            'Aperture',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
}

function Resolve-NatureAILibrary {
    param([switch]$ForceSelection)
    if (-not $ForceSelection) {
        $saved = Read-NatureAILibrary
        if ($saved) { return $saved }
    }
    return Select-NatureAILibrary
}
'@
    $commonScript = $commonScript.Replace('__DATA_ROOT__', $DataRoot.Replace("'", "''"))
    $commonScript = $commonScript.Replace('__ADMIN_EXECUTABLE__', $adminExecutable.Replace("'", "''"))
    Set-Content -LiteralPath $commonPath -Value $commonScript -Encoding UTF8

    $apertureExecutable = Join-Path $EnvironmentPath 'Scripts\fieldora.exe'
    if (-not (Test-Path -LiteralPath $apertureExecutable -PathType Leaf)) {
        Fail "Fieldora GUI launcher was not installed: $apertureExecutable"
    }

    # Launch the GUI through Windows Script Host so a console window is never
    # attached to the lifetime of Aperture. The debug launcher below remains
    # available when console output is intentionally required.
    $apertureLauncherScript = Join-Path $launcherRoot 'start_aperture.vbs'
    $escapedExecutable = $apertureExecutable.Replace('"', '""')
    $escapedDataRoot = $DataRoot.Replace('"', '""')
    $apertureLauncherContent = @"
Option Explicit
Dim shell, environment
Set shell = CreateObject("WScript.Shell")
Set environment = shell.Environment("PROCESS")
environment("APERTURE_DATA_ROOT") = "$escapedDataRoot"
environment("NATUREAI_DATA_ROOT") = "$escapedDataRoot"
environment("HF_HOME") = "$escapedDataRoot\cache\huggingface"
environment("HUGGINGFACE_HUB_CACHE") = "$escapedDataRoot\cache\huggingface\hub"
environment("TORCH_HOME") = "$escapedDataRoot\cache\torch"
environment("XDG_CACHE_HOME") = "$escapedDataRoot\cache"
shell.Run Chr(34) & "$escapedExecutable" & Chr(34), 1, False
"@
    Set-Content -LiteralPath $apertureLauncherScript -Value $apertureLauncherContent -Encoding ASCII
    $windowsScriptHost = Join-Path $env:WINDIR 'System32\wscript.exe'
    if (-not (Test-Path -LiteralPath $windowsScriptHost -PathType Leaf)) { $windowsScriptHost = 'wscript.exe' }
    $apertureLauncher = $windowsScriptHost
    $apertureLauncherArguments = "//nologo `"$apertureLauncherScript`""

    $debugPath = Join-Path $launcherRoot 'start_natureai_next_debug.ps1'
    $debugScript = @'
. (Join-Path $PSScriptRoot 'launcher_common.ps1')
$library = Resolve-NatureAILibrary
if (-not $library) { exit 0 }

$sessionStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$sessionRoot = Join-Path $env:APERTURE_DATA_ROOT ("logs\debug-sessions\$sessionStamp")
New-Item -ItemType Directory -Force -Path $sessionRoot | Out-Null
$consoleLog = Join-Path $sessionRoot 'console.log'
$sessionMetadata = Join-Path $sessionRoot 'session.json'
$supportZip = Join-Path (Split-Path -Parent $sessionRoot) ("Aperture-debug-$sessionStamp.zip")
$applicationLog = Join-Path $env:APERTURE_DATA_ROOT 'logs\natureai-next.jsonl'
$launcherLogRoot = Join-Path $env:APERTURE_DATA_ROOT 'logs\launcher'
$executable = '__DESKTOP_EXECUTABLE__'

$metadata = [ordered]@{
    schema_version = 1
    started_at = (Get-Date).ToUniversalTime().ToString('o')
    aperture_version = '__APERTURE_VERSION__'
    executable = $executable
    library = $library
    data_root = $env:APERTURE_DATA_ROOT
    computer = $env:COMPUTERNAME
    windows = [Environment]::OSVersion.VersionString
    powershell = $PSVersionTable.PSVersion.ToString()
    python_environment = '__ENVIRONMENT_PATH__'
    command = @('--library', $library, '--log-level', 'DEBUG', '--diagnostics', '--no-update-check')
}
$metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sessionMetadata -Encoding UTF8

Write-Host "Aperture debug session: $sessionRoot" -ForegroundColor Cyan
Write-Host "Console log: $consoleLog"
Write-Host 'Close Aperture normally after reproducing the problem.' -ForegroundColor Yellow

$exitCode = 1
$stdoutLog = Join-Path $sessionRoot 'stdout.log'
$stderrLog = Join-Path $sessionRoot 'stderr.log'
try {
    $quotedLibrary = '"' + $library.Replace('"', '\"') + '"'
    $arguments = @('--library', $quotedLibrary, '--log-level', 'DEBUG', '--diagnostics', '--no-update-check')
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    $exitCode = $process.ExitCode
    @(
        '=== STANDARD OUTPUT ==='
        if (Test-Path -LiteralPath $stdoutLog) { Get-Content -LiteralPath $stdoutLog }
        '=== STANDARD ERROR ==='
        if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog }
    ) | Set-Content -LiteralPath $consoleLog -Encoding UTF8
    Get-Content -LiteralPath $consoleLog
}
catch {
    $_ | Out-String | Add-Content -LiteralPath $consoleLog -Encoding UTF8
    $exitCode = 1
}
finally {
    $finished = [ordered]@{
        finished_at = (Get-Date).ToUniversalTime().ToString('o')
        exit_code = $exitCode
    }
    $finished | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $sessionRoot 'result.json') -Encoding UTF8

    if (Test-Path -LiteralPath $applicationLog -PathType Leaf) {
        Copy-Item -LiteralPath $applicationLog -Destination (Join-Path $sessionRoot 'natureai-next.jsonl') -Force
    }
    if (Test-Path -LiteralPath $launcherLogRoot -PathType Container) {
        Copy-Item -LiteralPath $launcherLogRoot -Destination (Join-Path $sessionRoot 'launcher') -Recurse -Force
    }
    $installationConfig = Join-Path $env:APERTURE_DATA_ROOT 'config\installation.json'
    if (Test-Path -LiteralPath $installationConfig -PathType Leaf) {
        Copy-Item -LiteralPath $installationConfig -Destination (Join-Path $sessionRoot 'installation.json') -Force
    }
    try {
        Compress-Archive -LiteralPath (Join-Path $sessionRoot '*') -DestinationPath $supportZip -Force
        Write-Host "Support bundle: $supportZip" -ForegroundColor Green
    }
    catch {
        Write-Warning "The support ZIP could not be created: $($_.Exception.Message)"
    }
}

Write-Host "Aperture exited with code $exitCode."
if ($exitCode -ne 0) { Read-Host 'Press Enter to close' | Out-Null }
exit $exitCode
'@
    $debugScript = $debugScript.Replace('__DESKTOP_EXECUTABLE__', $desktopExecutable.Replace("'", "''"))
    $debugScript = $debugScript.Replace('__ENVIRONMENT_PATH__', $EnvironmentPath.Replace("'", "''"))
    $debugScript = $debugScript.Replace('__APERTURE_VERSION__', (Get-Content -LiteralPath (Join-Path $RepositoryRoot 'VERSION') -Raw).Trim().Replace("'", "''"))
    Set-Content -LiteralPath $debugPath -Value $debugScript -Encoding UTF8

    $selectPath = Join-Path $launcherRoot 'select_natureai_library.ps1'
    $selectScript = @'
. (Join-Path $PSScriptRoot 'launcher_common.ps1')
$library = Resolve-NatureAILibrary -ForceSelection
if ($library) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Default library set to:`n$library",
        'Aperture',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}
'@
    Set-Content -LiteralPath $selectPath -Value $selectScript -Encoding UTF8


    $maintenancePath = Join-Path $launcherRoot 'start_maintenance_center.ps1'
    $maintenanceScript = @'
. (Join-Path $PSScriptRoot 'launcher_common.ps1')
$library = Resolve-NatureAILibrary
if (-not $library) { exit 0 }
$executable = '__MAINTENANCE_EXECUTABLE__'
& $executable --library $library
exit $LASTEXITCODE
'@
    $maintenanceScript = $maintenanceScript.Replace('__MAINTENANCE_EXECUTABLE__', $maintenanceExecutable.Replace("'", "''"))
    Set-Content -LiteralPath $maintenancePath -Value $maintenanceScript -Encoding UTF8

    $adminPath = Join-Path $launcherRoot 'start_admin_console.cmd'
    $adminScript = @"
@echo off
set "APERTURE_DATA_ROOT=$DataRoot"
set "NATUREAI_DATA_ROOT=$DataRoot"
set "HF_HOME=$DataRoot\cache\huggingface"
set "HUGGINGFACE_HUB_CACHE=$DataRoot\cache\huggingface\hub"
set "TORCH_HOME=$DataRoot\cache\torch"
set "XDG_CACHE_HOME=$DataRoot\cache"
set "PATH=$EnvironmentPath\Scripts;$EnvironmentPath;%PATH%"
title Aperture Admin Console - NatureAI_Next
cd /d "%USERPROFILE%"
echo Aperture Admin Console - powered by NatureAI_Next
echo Type natureai-next-admin --help to list commands.
echo.
cmd /k
"@
    Set-Content -LiteralPath $adminPath -Value $adminScript -Encoding ASCII

    if ($InitialLibrary) {
        $resolvedLibrary = [System.IO.Path]::GetFullPath($InitialLibrary)
        if (-not ((Test-Path -LiteralPath (Join-Path $resolvedLibrary 'library.json') -PathType Leaf) -and
                  (Test-Path -LiteralPath (Join-Path $resolvedLibrary 'library.sqlite3') -PathType Leaf))) {
            Fail "Default library is not an initialized NatureAI Next library: $resolvedLibrary"
        }
        $configurationPath = Join-Path $configurationRoot 'launcher.json'
        $temporaryPath = "$configurationPath.tmp"
        @{ schema_version = 1; last_library = $resolvedLibrary } |
            ConvertTo-Json |
            Set-Content -LiteralPath $temporaryPath -Encoding UTF8
        Move-Item -LiteralPath $temporaryPath -Destination $configurationPath -Force
    }

    $powerShellExecutable = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powerShellExecutable -PathType Leaf)) {
        $powerShellExecutable = 'powershell.exe'
    }
    $apertureIcon = Join-Path $RepositoryRoot 'resources\fieldora.ico'
    $shortcutIcon = if (Test-Path -LiteralPath $apertureIcon -PathType Leaf) { $apertureIcon } else { $desktopExecutable }
    $recoveryIcon = Join-Path $RepositoryRoot 'resources\aperture-backup-recovery.ico'
    if (-not (Test-Path -LiteralPath $recoveryIcon -PathType Leaf)) { $recoveryIcon = $shortcutIcon }
    # Previous labels remain documented for installer compatibility gates:
    # @{ Name = 'Fieldora'; Target = $apertureLauncher
    # @{ Name = 'Fieldora (Debug)'; Target = $powerShellExecutable
    # Name = 'Fieldora Maintenance Center'; Target = $powerShellExecutable
    $shortcutDefinitions = @(
        @{ Name = 'Fieldora V5'; Target = $apertureLauncher; Arguments = $apertureLauncherArguments; Description = 'Start Fieldora — offline biodiversity research and scientific projects' },
        @{ Name = 'Fieldora V5 (Debug)'; Target = $powerShellExecutable; Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$debugPath`""; Description = 'Start Fieldora with NatureAI_Next debug logging' },
        @{ Name = 'Fieldora V5 - Select Library'; Target = $powerShellExecutable; Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$selectPath`""; Description = 'Choose the default NatureAI Next library for Fieldora' },
        @{ Name = 'Fieldora V5 Maintenance Center'; Target = $powerShellExecutable; Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$maintenancePath`""; Description = 'Update, back up, restore, repair, and inspect Fieldora'; Icon = $recoveryIcon },
        @{ Name = 'NatureAI Next Admin Console'; Target = $adminPath; Arguments = ''; Description = 'Open the NatureAI Next administrative console' }
    )

    if ($DesktopShortcuts) {
        $desktopDirectory = [Environment]::GetFolderPath('Desktop')
        foreach ($definition in $shortcutDefinitions[0..3]) {
            $definitionIcon = if ($definition.ContainsKey('Icon')) { $definition.Icon } else { $shortcutIcon }
            New-WindowsShortcut -Path (Join-Path $desktopDirectory ($definition.Name + '.lnk')) -TargetPath $definition.Target -Arguments $definition.Arguments -WorkingDirectory $launcherRoot -Description $definition.Description -IconLocation "$definitionIcon,0"
        }
    }

    if ($StartMenuShortcuts) {
        $startMenuDirectory = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Fieldora V5'
        New-Item -ItemType Directory -Force -Path $startMenuDirectory | Out-Null
        foreach ($definition in $shortcutDefinitions) {
            $definitionIcon = if ($definition.ContainsKey('Icon')) { $definition.Icon } else { $shortcutIcon }
            New-WindowsShortcut -Path (Join-Path $startMenuDirectory ($definition.Name + '.lnk')) -TargetPath $definition.Target -Arguments $definition.Arguments -WorkingDirectory $launcherRoot -Description $definition.Description -IconLocation "$definitionIcon,0"
        }
    }

    Write-Host "Launchers:    $launcherRoot"
    if ($InitialLibrary) { Write-Host "Default library: $InitialLibrary" }
    else { Write-Host 'Default library: select on first launch' }
}

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $DataRoot) { $DataRoot = Join-Path $RepositoryRoot 'FieldoraData-V5' }
$script:DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$DataRoot = $script:DataRoot

# Validate the immutable release before creating ApertureData, cache folders,
# installation configuration, or any other mutable installation state.
$preflightReportPath = Join-Path $RepositoryRoot '.installation\deployment-preflight.json'
if (-not $SkipDeploymentPreflight) {
    Write-Step 'Validating release package before installation'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $preflightReportPath) | Out-Null
    $preflightConda = Ensure-CondaExecutable
    & $preflightConda run --no-capture-output -n base python (Join-Path $PSScriptRoot 'deployment_preflight.py') --release-root $RepositoryRoot --output $preflightReportPath
    if ($LASTEXITCODE -ne 0) { Fail 'Release package preflight failed. No Aperture data or installation configuration was created.' }
}

New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$env:APERTURE_DATA_ROOT = $DataRoot
$env:NATUREAI_DATA_ROOT = $DataRoot
$env:HF_HOME = Join-Path $DataRoot 'cache\huggingface'
$env:HUGGINGFACE_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:TORCH_HOME = Join-Path $DataRoot 'cache\torch'
$env:XDG_CACHE_HOME = Join-Path $DataRoot 'cache'
foreach ($directory in @($env:HF_HOME, $env:HUGGINGFACE_HUB_CACHE, $env:TORCH_HOME, $env:XDG_CACHE_HOME)) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
$configRoot = Join-Path $DataRoot 'config'
New-Item -ItemType Directory -Force -Path $configRoot | Out-Null
$installationConfig = [ordered]@{
    schema_version = 1
    version = (Get-Content -LiteralPath (Join-Path $RepositoryRoot 'VERSION') -Raw).Trim()
    installation_root = $RepositoryRoot
    data_root = $DataRoot
    model_root = (Join-Path $DataRoot 'models')
    cache_root = (Join-Path $DataRoot 'cache')
    logs_root = (Join-Path $DataRoot 'logs')
    created_at = (Get-Date).ToString('o')
}
$installationConfig | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $configRoot 'installation.json') -Encoding UTF8
$PyProject = Join-Path $RepositoryRoot 'pyproject.toml'
$RequirementsRoot = Join-Path $RepositoryRoot 'requirements'
if (-not (Test-Path -LiteralPath $PyProject -PathType Leaf)) {
    Fail "pyproject.toml was not found at $PyProject."
}
if (-not (Test-Path -LiteralPath $RequirementsRoot -PathType Container)) {
    Fail "requirements directory was not found at $RequirementsRoot."
}
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Fail 'PowerShell 5.1 or newer is required.'
}
if ($env:OS -ne 'Windows_NT') {
    Fail 'This installer is intended for Windows.'
}
if ($InstallProfile -eq 'Full') {
    $InstallProfile = 'FullAI'
}

$script:CondaExecutable = Resolve-CondaExecutable
if ($null -eq $script:CondaExecutable) { $script:CondaExecutable = Install-MinicondaBootstrap }
Write-Step "Using Conda: $script:CondaExecutable"
& $script:CondaExecutable --version
if ($LASTEXITCODE -ne 0) {
    Fail 'Conda could not be executed.'
}

$environmentPath = Get-EnvironmentRecord
if ($null -ne $environmentPath -and $RecreateEnvironment) {
    Write-Step "Removing existing isolated environment '$EnvironmentName'"
    # Conda 26's Terms-of-Service plugin evaluates configured channels for
    # environment removal.  The installer never consumes Anaconda's default
    # repositories, so keep removal on the same explicit conda-forge policy as
    # creation and package installation.  This avoids asking users to accept
    # terms for channels Aperture does not use.
    Invoke-Conda -Arguments @(
        'remove', '--all', '--yes', '--name', $EnvironmentName,
        '--override-channels', '--channel', 'conda-forge'
    )
    $environmentPath = $null
}

if ($null -eq $environmentPath) {
    Write-Step "Creating isolated Python 3.11 environment '$EnvironmentName'"
    Invoke-Conda -Arguments @(
        'create', '--yes', '--name', $EnvironmentName,
        '--override-channels', '--channel', 'conda-forge', '--strict-channel-priority',
        'python=3.11', 'pip=24.*', 'setuptools', 'wheel'
    )
}
else {
    Write-Step "Reusing existing isolated environment '$EnvironmentName'"
}

$environmentPath = Get-EnvironmentRecord
if ($null -eq $environmentPath) {
    Fail "The Conda environment '$EnvironmentName' could not be resolved after creation."
}
$environmentPython = Join-Path $environmentPath 'python.exe'
if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
    Fail "Python was not found at $environmentPython."
}

Write-Step 'Verifying Python 3.11'
Invoke-InEnvironment -Arguments @(
    'python', '-c',
    'import sys; assert sys.version_info[:2] == (3, 11), "Expected Python 3.11, got " + sys.version; print(sys.version)'
)

Push-Location $RepositoryRoot
try {
    if (-not $SkipDependencyInstallation) {
    Write-Step 'Installing core and GUI dependencies'
    $baseRequirements = if ($InstallProfile -eq 'Core') { 'core.txt' } else { 'gui.txt' }
    Invoke-InEnvironment -Arguments @(
        'python', '-m', 'pip', 'install',
        '--requirement', (Join-Path 'requirements' $baseRequirements)
    )

    if ($InstallProfile -eq 'FullAI') {
        Write-Step 'Installing compiled HNSWLib through Conda Forge'
        Invoke-Conda -Arguments @(
            'install', '--yes', '--name', $EnvironmentName,
            '--override-channels', '--channel', 'conda-forge', '--strict-channel-priority',
            'hnswlib=0.8.0'
        )

        Write-Step "Installing PyTorch runtime ($TorchBuild)"
        Invoke-InEnvironment -Arguments @(
            'python', '-m', 'pip', 'uninstall', '--yes',
            'torch', 'torchvision', 'torchaudio'
        )

        if ($TorchBuild -eq 'CUDA124') {
            Invoke-InEnvironment -Arguments @(
                'python', '-m', 'pip', 'install',
                'torch==2.5.1', 'torchvision==0.20.1', 'torchaudio==2.5.1',
                '--index-url', 'https://download.pytorch.org/whl/cu124'
            )
        }
        else {
            Invoke-InEnvironment -Arguments @(
                'python', '-m', 'pip', 'install',
                'torch==2.5.1', 'torchvision==0.20.1', 'torchaudio==2.5.1',
                '--index-url', 'https://download.pytorch.org/whl/cpu'
            )
        }

        Write-Step 'Installing OpenCLIP'
        Invoke-InEnvironment -Arguments @(
            'python', '-m', 'pip', 'install',
            '--constraint', (Join-Path 'requirements' 'constraints-py311.txt'),
            'open-clip-torch==2.30.0'
        )

        Write-Step 'Installing the NatureAI BioCLIP Tree-of-Life runtime'
        Invoke-InEnvironment -Arguments @(
            'python', '-m', 'pip', 'install',
            '--constraint', (Join-Path 'requirements' 'constraints-py311.txt'),
            'pybioclip==2.1.5', 'huggingface-hub>=0.27,<1'
        )
    }

    if ($IncludeDevelopmentTools) {
        Write-Step 'Installing development and validation tools'
        Invoke-InEnvironment -Arguments @(
            'python', '-m', 'pip', 'install',
            '--requirement', (Join-Path 'requirements' 'dev.txt')
        )
    }
    }

    if (-not $SkipPackageInstallation) {
    Write-Step 'Removing the previous NatureAI Next code package'
    # A clean uninstall is deliberate: stale Python modules from an older PMTiles
    # renderer must not survive an in-place source upgrade. User libraries and
    # external map/taxonomy databases are outside the environment and untouched.
    Invoke-InEnvironment -Arguments @('python', '-m', 'pip', 'uninstall', '--yes', 'natureai-next')

    Write-Step 'Installing NatureAI Next'
    $packageArguments = @('python', '-m', 'pip', 'install', '--no-deps', '--force-reinstall', '--no-cache-dir')
    if ($Editable) {
        $packageArguments += '--editable'
    }
    $packageArguments += '.'
    Invoke-InEnvironment -Arguments $packageArguments
    }
}
finally {
    Pop-Location
}

Write-Step 'Writing installation report'
$reportDirectory = Join-Path $RepositoryRoot '.installation'
New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
$reportPath = Join-Path $reportDirectory 'environment.txt'
$freezePath = Join-Path $reportDirectory 'pip-freeze.txt'
$reportScriptPath = Join-Path $reportDirectory 'write_environment_report.py'
$reportScript = @'
import platform
import sys

import natureai_next

print(f"NatureAI Next: {natureai_next.__version__}")
print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")
print(f"Platform: {platform.platform()}")
'@
Set-Content -LiteralPath $reportScriptPath -Value $reportScript -Encoding UTF8

$report = & $environmentPython $reportScriptPath
if ($LASTEXITCODE -ne 0) {
    Fail 'The installed package could not be imported.'
}
$report | Set-Content -LiteralPath $reportPath -Encoding UTF8
$report | Write-Host

$freeze = & $environmentPython -m pip freeze --all
if ($LASTEXITCODE -ne 0) {
    Fail 'Unable to capture the installed package inventory.'
}
$freeze | Set-Content -LiteralPath $freezePath -Encoding UTF8

if (-not $SkipSmokeTest) {
    Write-Step 'Running installation smoke tests'
    Invoke-InEnvironment -Arguments @('natureai-next', '--help')
    Invoke-InEnvironment -Arguments @('natureai-next-admin', '--help')
    Invoke-InEnvironment -Arguments @('natureai-next-resources', '--help')

    $verifyArguments = @('python', 'scripts\verify_install.py')
    if ($InstallProfile -in @('GUI', 'FullAI')) {
        $verifyArguments += '--require-gui'
    }
    if ($InstallProfile -eq 'FullAI') {
        $verifyArguments += '--require-ai'
    }
    if ($InstallProfile -eq 'FullAI') {
        Write-Step 'Acquiring and validating BioCLIP TreeOfLife-10M resources'
        Push-Location $RepositoryRoot
        try {
            Invoke-InEnvironment -Arguments @('python', 'scripts\bootstrap_bioclip_tree_of_life.py')
        }
        finally {
            Pop-Location
        }
    }
    Push-Location $RepositoryRoot
    try {
        Invoke-InEnvironment -Arguments $verifyArguments
    }
    finally {
        Pop-Location
    }
}

if ($RunValidation) {
    if (-not $IncludeDevelopmentTools) {
        Fail '-RunValidation requires -IncludeDevelopmentTools.'
    }
    Write-Step 'Running repository validation'
    Push-Location $RepositoryRoot
    try {
        Invoke-InEnvironment -Arguments @('python', 'scripts\validate.py')
    }
    finally {
        Pop-Location
    }
}

if ($AddEnvironmentToUserPath) {
    Write-Step 'Adding NatureAI Next commands to the current user PATH'
    Add-NatureAIUserPath -EnvironmentPath $environmentPath
}

if (-not $DefaultLibrary) {
    $DefaultLibrary = Join-Path (Split-Path -Parent $DataRoot) 'Fieldora-Library-V5'
    $CreateDefaultLibrary = $true
}

if ($CreateDefaultLibrary) {
    $manifestCandidate = Join-Path $DefaultLibrary 'library.json'
    $databaseCandidate = Join-Path $DefaultLibrary 'library.sqlite3'
    if ((Test-Path -LiteralPath $manifestCandidate -PathType Leaf) -or (Test-Path -LiteralPath $databaseCandidate -PathType Leaf)) {
        Fail "A clean library was requested but library files already exist at $DefaultLibrary."
    }
    Write-Step "Creating and validating the Aperture Library at $DefaultLibrary"
    $libraryParent = Split-Path -Parent $DefaultLibrary
    if (-not (Test-Path -LiteralPath $libraryParent -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $libraryParent | Out-Null
    }
    Invoke-InEnvironment -Arguments @('natureai-next-admin', 'library-create', $DefaultLibrary, '--name', 'Aperture Library', '--locale', 'en')
    Invoke-InEnvironment -Arguments @('natureai-next-admin', 'library-check', $DefaultLibrary)
}
else {
    if (-not (Test-Path -LiteralPath (Join-Path $DefaultLibrary 'library.json') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $DefaultLibrary 'library.sqlite3') -PathType Leaf)) {
        Fail "The selected existing Aperture Library is incomplete: $DefaultLibrary"
    }
}

$resolvedDefaultLibrary = [System.IO.Path]::GetFullPath($DefaultLibrary)
$resolvedDataRoot = [System.IO.Path]::GetFullPath($DataRoot)
if ($resolvedDefaultLibrary -eq $resolvedDataRoot -or
    $resolvedDefaultLibrary.StartsWith($resolvedDataRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
    $resolvedDataRoot.StartsWith($resolvedDefaultLibrary + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail 'The default library and FieldoraData-V5 must be separate, non-nested directories.'
}

Write-Step 'Installing Windows launchers and shortcuts'
Install-WindowsLaunchers -EnvironmentPath $environmentPath -DataRoot $DataRoot -InitialLibrary $DefaultLibrary -DesktopShortcuts $CreateDesktopShortcuts -StartMenuShortcuts $CreateStartMenuShortcuts

Write-Step 'Registering NatureAI Next with Windows Installed Apps'
$installedVersion = (& $environmentPython -c 'import natureai_next; print(natureai_next.__version__)').Trim()
if ($LASTEXITCODE -ne 0 -or -not $installedVersion) { Fail 'Unable to determine the installed NatureAI Next version.' }
$launcherRoot = Join-Path $DataRoot 'launchers'
Register-WindowsApplication -RepositoryRoot $RepositoryRoot -EnvironmentPath $environmentPath -LauncherRoot $launcherRoot -DataRoot $DataRoot -Version $installedVersion

Write-Step 'Installation completed'
Write-Host "Environment: $EnvironmentName"
Write-Host "Profile:     $InstallProfile"
Write-Host "Repository:  $RepositoryRoot"
Write-Host "Data root:   $DataRoot"
Write-Host "Report:      $reportPath"
Write-Host "Inventory:   $freezePath"
Write-Host ''
Write-Host 'The installer does not modify or remove NatureAI Legacy.' -ForegroundColor Green
Write-Host 'Libraries, photographs, models, backups, and exports remain outside the Conda environment.' -ForegroundColor Green
