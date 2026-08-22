[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$EnvironmentName = 'fieldora-v5',

    [switch]$RemoveEnvironment,
    [switch]$RemoveInstallationReports,
    [switch]$RemoveApplicationData,

    [switch]$StopRunningProcesses,

    [string]$InstallationRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-NatureAIEnvironmentPath {
    param([Parameter(Mandatory)][string]$EnvironmentName)

    $candidateRoots = @(
        (Join-Path $env:LOCALAPPDATA 'miniconda3'),
        (Join-Path $env:LOCALAPPDATA 'anaconda3'),
        (Join-Path $env:USERPROFILE 'miniconda3'),
        (Join-Path $env:USERPROFILE 'anaconda3'),
        'C:\ProgramData\miniconda3',
        'C:\ProgramData\anaconda3'
    )

    foreach ($root in $candidateRoots) {
        $candidate = Join-Path $root (Join-Path 'envs' $EnvironmentName)
        if ((Test-Path -LiteralPath $candidate -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'python.exe') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'conda-meta') -PathType Container)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $pathEntries = @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';')
    foreach ($entry in $pathEntries) {
        if (-not $entry) { continue }
        $candidate = $entry.TrimEnd('\\')
        if ((Split-Path -Leaf $candidate) -eq 'Scripts') {
            $candidate = Split-Path -Parent $candidate
        }
        if ((Split-Path -Leaf $candidate) -eq $EnvironmentName -and
            (Test-Path -LiteralPath (Join-Path $candidate 'python.exe') -PathType Leaf)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    return $null
}

function Get-ApertureEnvironmentProcesses {
    param([Parameter(Mandatory)][string]$EnvironmentPath)

    $normalized = [System.IO.Path]::GetFullPath($EnvironmentPath).TrimEnd('\\')
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -and $exe.StartsWith($normalized, [System.StringComparison]::OrdinalIgnoreCase)) -or
        ($cmd -and $cmd.IndexOf($normalized, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    })
}

function Get-ApertureProcessLabel {
    param([Parameter(Mandatory)]$Process)

    $command = [string]$Process.CommandLine
    if ($command -match 'native_updater') { return 'Aperture Updater' }
    if ($command -match 'native_recovery') { return 'Aperture Recovery' }
    if ($command -match 'maintenance_center') { return 'Aperture Maintenance Center' }
    if ($command -match 'natureai_next\.bootstrap\.(cli|aperture_launcher)') { return 'Aperture' }
    if ($command -match 'BioCLIP|open_clip|natureai_next\.infrastructure\.ai') { return 'NatureAI Engine' }
    return 'Aperture Background Service'
}

function Stop-ApertureEnvironmentProcesses {
    param(
        [Parameter(Mandatory)][string]$EnvironmentPath,
        [switch]$Force
    )

    $normalized = [System.IO.Path]::GetFullPath($EnvironmentPath).TrimEnd('\')
    $running = @(Get-ApertureEnvironmentProcesses -EnvironmentPath $EnvironmentPath)

    if ($running.Count -gt 0) {
        $details = ($running | ForEach-Object { "$(Get-ApertureProcessLabel -Process $_) (PID $($_.ProcessId), $($_.Name))" }) -join ', '
        if (-not $Force) {
            throw "Aperture work is still running: $details. Close Aperture and Maintenance Center, or use the full-environment uninstall option to stop managed processes safely."
        }

        Write-Host "Requesting managed Aperture processes to close: $details" -ForegroundColor Yellow
        foreach ($item in $running) {
            $process = Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
            if ($process -and $process.MainWindowHandle -ne 0) {
                [void]$process.CloseMainWindow()
            }
        }
        $deadline = (Get-Date).AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 250
            $remaining = @(Get-ApertureEnvironmentProcesses -EnvironmentPath $EnvironmentPath)
        } while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline)

        if ($remaining.Count -gt 0) {
            Write-Host "Stopping $($remaining.Count) remaining managed background process(es)." -ForegroundColor Yellow
            foreach ($item in $remaining) {
                $executable = [string]$item.ExecutablePath
                if ($executable -and $executable.StartsWith($normalized, [System.StringComparison]::OrdinalIgnoreCase)) {
                    Stop-Process -Id $item.ProcessId -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Milliseconds 500
        }
        $remaining = @(Get-ApertureEnvironmentProcesses -EnvironmentPath $EnvironmentPath)
        if ($remaining.Count -gt 0) {
            $blocked = ($remaining | ForEach-Object { "$(Get-ApertureProcessLabel -Process $_) (PID $($_.ProcessId))" }) -join ', '
            throw "Managed Aperture processes could not be stopped: $blocked. Restart Windows, then run uninstall again."
        }
    }
}

function Remove-DirectoryWithRetry {
    param([Parameter(Mandatory)][string]$Path)

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            if (Test-Path -LiteralPath $Path) {
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            }
            return
        }
        catch {
            if ($attempt -eq 5) { throw }
            Start-Sleep -Milliseconds (500 * $attempt)
        }
    }
}

function Remove-NatureAIUserPath {
    param([Parameter(Mandatory)][string]$EnvironmentPath)
    $targets = @(
        (Join-Path $EnvironmentPath 'Scripts'),
        $EnvironmentPath
    ) | ForEach-Object { [System.IO.Path]::GetFullPath($_).TrimEnd('\') }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { return }
    $kept = @()
    foreach ($entry in ($userPath -split ';')) {
        if (-not $entry.Trim()) { continue }
        $normalized = $null
        try { $normalized = [System.IO.Path]::GetFullPath($entry).TrimEnd('\') } catch { $normalized = $entry.TrimEnd('\') }
        if (-not ($targets | Where-Object { $_.Equals($normalized, [System.StringComparison]::OrdinalIgnoreCase) })) {
            $kept += $entry
        }
    }
    [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')
}

$RepositoryRoot = if ($InstallationRoot) { [System.IO.Path]::GetFullPath($InstallationRoot) } else { (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
$environmentRecord = Resolve-NatureAIEnvironmentPath -EnvironmentName $EnvironmentName
if ($environmentRecord) { Remove-NatureAIUserPath -EnvironmentPath ([string]$environmentRecord) }

Write-Host 'Fieldora uninstaller' -ForegroundColor Cyan
Write-Host 'This script never removes NatureAI libraries, photographs, model archives, backups, or exports.' -ForegroundColor Yellow

if ($RemoveEnvironment) {
    if ($PSCmdlet.ShouldProcess("Conda environment '$EnvironmentName'", 'Remove entire environment')) {
        if (-not $environmentRecord) {
            Write-Host "The NatureAI_Next environment '$EnvironmentName' was not found; continuing cleanup." -ForegroundColor Yellow
        }
        else {
            Stop-ApertureEnvironmentProcesses -EnvironmentPath ([string]$environmentRecord) -Force:$StopRunningProcesses
            Remove-DirectoryWithRetry -Path ([string]$environmentRecord)
        }
    }
}
else {
    if ($PSCmdlet.ShouldProcess("NatureAI Next package in '$EnvironmentName'", 'Uninstall package')) {
        if (-not $environmentRecord) {
            throw "NatureAI_Next environment '$EnvironmentName' was not found."
        }
        Stop-ApertureEnvironmentProcesses -EnvironmentPath ([string]$environmentRecord)
        $environmentPython = Join-Path ([string]$environmentRecord) 'python.exe'
        & $environmentPython -m pip uninstall --yes natureai-next
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to uninstall NatureAI_Next from '$EnvironmentName'."
        }
    }
}


$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$shortcutNames = @(
    'Fieldora V5.lnk',
    'Fieldora V5 (Debug).lnk',
    'Fieldora V5 - Select Library.lnk',
    'Fieldora V5 Maintenance Center.lnk',
    'Repair Fieldora V5.lnk',
    'Uninstall Fieldora V5.lnk',
    'Fieldora.lnk',
    'Fieldora (Debug).lnk',
    'Fieldora - Select Library.lnk',
    'Fieldora Maintenance Center.lnk',
    'Repair Fieldora.lnk',
    'Uninstall Fieldora.lnk',
    'Aperture.lnk',
    'Aperture (Debug).lnk',
    'Aperture - Select Library.lnk',
    'Aperture Maintenance Center.lnk',
    'Repair Aperture.lnk',
    'Uninstall Aperture.lnk',
    'NatureAI Next.lnk',
    'NatureAI Next (Debug).lnk',
    'NatureAI Next - Select Library.lnk',
    'NatureAI Next Admin Console.lnk',
    'Repair NatureAI Next.lnk',
    'Uninstall NatureAI Next.lnk'
)
foreach ($shortcutName in $shortcutNames) {
    $shortcutPath = Join-Path $desktopDirectory $shortcutName
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        if ($PSCmdlet.ShouldProcess($shortcutPath, 'Remove NatureAI Next desktop shortcut')) {
            Remove-Item -LiteralPath $shortcutPath -Force
        }
    }
}
$pinnedShortcutDirectory = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
foreach ($shortcutName in $shortcutNames) {
    $shortcutPath = Join-Path $pinnedShortcutDirectory $shortcutName
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        if ($PSCmdlet.ShouldProcess($shortcutPath, 'Remove Fieldora pinned shortcut')) {
            Remove-Item -LiteralPath $shortcutPath -Force
        }
    }
}
$startMenuDirectories = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Fieldora V5'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Fieldora'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Aperture'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\NatureAI Next')
)
foreach ($startMenuDirectory in $startMenuDirectories)
{
    if (Test-Path -LiteralPath $startMenuDirectory -PathType Container) {
        if ($PSCmdlet.ShouldProcess($startMenuDirectory, 'Remove Fieldora / Aperture / NatureAI Next Start Menu shortcuts')) {
            Remove-Item -LiteralPath $startMenuDirectory -Recurse -Force
        }
    }
}
$launcherRoots = @(
    (Join-Path $RepositoryRoot 'FieldoraData-V5\launchers'),
    (Join-Path $env:LOCALAPPDATA 'NatureAI\NatureAI Next\Launchers')
)
if ((Split-Path -Leaf $PSScriptRoot) -ieq 'launchers') {
    $launcherRoots += $PSScriptRoot
}
foreach ($launcherRoot in ($launcherRoots | Select-Object -Unique)) {
    if (Test-Path -LiteralPath $launcherRoot -PathType Container) {
        if ($PSCmdlet.ShouldProcess($launcherRoot, 'Remove machine-local NatureAI Next launchers and Fieldora V5 launchers')) {
            Remove-DirectoryWithRetry -Path $launcherRoot
        }
    }
}

$registrationRoots = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Fieldora V5',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Fieldora',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Aperture',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NatureAI Next'
)
foreach ($registrationRoot in $registrationRoots) {
    if (Test-Path -LiteralPath $registrationRoot) {
        if ($PSCmdlet.ShouldProcess($registrationRoot, 'Remove Fieldora Installed Apps registration')) {
            Remove-Item -LiteralPath $registrationRoot -Recurse -Force
        }
    }
}

$iconRefresh = Join-Path $env:SystemRoot 'System32\ie4uinit.exe'
if (Test-Path -LiteralPath $iconRefresh -PathType Leaf) {
    & $iconRefresh -show 2>$null
}

if ($RemoveInstallationReports) {
    $reportDirectory = Join-Path $RepositoryRoot '.installation'
    if (Test-Path -LiteralPath $reportDirectory) {
        if ($PSCmdlet.ShouldProcess($reportDirectory, 'Remove installation reports')) {
            Remove-Item -LiteralPath $reportDirectory -Recurse -Force
        }
    }
}

if ($RemoveApplicationData) {
    $localData = Join-Path $env:LOCALAPPDATA 'NatureAI\NatureAI Next'
    $roamingData = Join-Path $env:APPDATA 'NatureAI\NatureAI Next'
    foreach ($path in @($localData, $roamingData)) {
        if (Test-Path -LiteralPath $path) {
            if ($PSCmdlet.ShouldProcess($path, 'Remove application configuration, logs, caches, plugins, and installed model registry data')) {
                Remove-Item -LiteralPath $path -Recurse -Force
            }
        }
    }
}

Write-Host 'Uninstall operation completed.' -ForegroundColor Green
Write-Host 'Source folders can be deleted manually after confirming no needed files remain.'
Write-Host 'NatureAI libraries and source photographs were not touched.'
