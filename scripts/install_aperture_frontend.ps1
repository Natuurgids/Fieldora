[CmdletBinding()]
param(
    [string[]]$InstallerArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Title {
    Clear-Host
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '                  Install Aperture' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ''
}


function Resolve-ApertureCondaExecutable {
    foreach ($name in @('conda.exe', 'conda')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command -and $command.CommandType -eq 'Application') {
            return $command.Source
        }
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:LOCALAPPDATA 'anaconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'),
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

function Parse-InstallerArguments {
    param([string[]]$Values)
    $result = @{
        Silent = $false
        Drive = $null
        Profile = 'FullAI'
        TorchBuild = 'CUDA124'
        Library = $null
        UseExisting = $false
        CreateNew = $false
        Repair = $false
        SkipDeploymentPreflight = $false
    }
    foreach ($value in $Values) {
        if ($value -ieq '/silent') { $result.Silent = $true; continue }
        if ($value -ieq '/useexisting') { $result.UseExisting = $true; continue }
        if ($value -ieq '/createnew') { $result.CreateNew = $true; continue }
        if ($value -ieq '/repair') { $result.Repair = $true; continue }
        if ($value -ieq '/skippreflight') { $result.SkipDeploymentPreflight = $true; continue }
        if ($value -match '^/drive=(.+)$') { $result.Drive = $Matches[1].TrimEnd(':','\') + ':'; continue }
        if ($value -match '^/profile=(.+)$') { $result.Profile = $Matches[1]; continue }
        if ($value -match '^/torch=(.+)$') { $result.TorchBuild = $Matches[1]; continue }
        if ($value -match '^/library=(.+)$') { $result.Library = $Matches[1].Trim('"'); continue }
        throw "Unknown installer option: $value"
    }
    if ($result.Profile -notin @('Core','GUI','Full','FullAI')) { throw "Unsupported profile: $($result.Profile)" }
    if ($result.TorchBuild -notin @('CUDA124','CPU')) { throw "Unsupported Torch build: $($result.TorchBuild)" }
    return $result
}

function Get-CandidateDrives {
    $items = @()
    foreach ($drive in [System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' -and $_.IsReady }) {
        $root = $drive.RootDirectory.FullName
        $target = Join-Path $root 'Fieldora-Library-V5'
        $writable = $false
        try {
            $probeDirectory = if (Test-Path -LiteralPath $target -PathType Container) { $target } else { $root }
            $probe = Join-Path $probeDirectory ('.aperture-write-test-' + [guid]::NewGuid().ToString('N'))
            [System.IO.File]::WriteAllText($probe, 'test')
            Remove-Item -LiteralPath $probe -Force
            $writable = $true
        } catch { }
        $items += [pscustomobject]@{
            Drive = $drive.Name.Substring(0,2)
            Root = $root
            FreeBytes = [int64]$drive.AvailableFreeSpace
            FreeGB = [math]::Round(([double]$drive.AvailableFreeSpace / 1GB), 1)
            Writable = $writable
            ExistingLibrary = (Test-Path -LiteralPath (Join-Path $target 'library.json') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $target 'library.sqlite3') -PathType Leaf)
        }
    }
    return @($items | Sort-Object -Property @{Expression='ExistingLibrary';Descending=$true}, @{Expression='Writable';Descending=$true}, @{Expression='FreeBytes';Descending=$true})
}

function Select-StorageDrive {
    param([object[]]$Drives)
    if (-not $Drives) { throw 'No writable fixed drive was found.' }
    Write-Host 'Where would you like Aperture to store your observations and AI data?' -ForegroundColor White
    Write-Host 'The Aperture Library contains the database, metadata, thumbnails, backups, and managed photographs.'
    Write-Host 'It grows over time, so choose a drive with sufficient free space.'
    Write-Host ''
    for ($index = 0; $index -lt $Drives.Count; $index++) {
        $drive = $Drives[$index]
        $flags = @()
        if ($index -eq 0) { $flags += 'recommended' }
        if ($drive.ExistingLibrary) { $flags += 'existing Aperture Library found' }
        if (-not $drive.Writable) { $flags += 'not writable without elevated permission' }
        $suffix = if ($flags) { ' - ' + ($flags -join ', ') } else { '' }
        Write-Host (" {0}. {1} ({2} GB free){3}" -f ($index + 1), $drive.Drive, $drive.FreeGB, $suffix)
    }
    Write-Host ''
    while ($true) {
        $choice = Read-Host "Choose a drive [1-$($Drives.Count)] (Enter for recommended)"
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $recommended = $Drives | Where-Object Writable | Select-Object -First 1
            if ($recommended) { return $recommended }
            throw 'No writable fixed drive was found.'
        }
        $number = 0
        if ([int]::TryParse($choice, [ref]$number) -and $number -ge 1 -and $number -le $Drives.Count) {
            $selected = $Drives[$number - 1]
            if (-not $selected.Writable) { Write-Host 'That drive is not writable from this installer session. Choose another drive or run the installer with elevated permissions.' -ForegroundColor Yellow; continue }
            return $selected
        }
        Write-Host 'Please enter a valid number.' -ForegroundColor Yellow
    }
}

$options = Parse-InstallerArguments -Values $InstallerArguments
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$installScript = Join-Path $PSScriptRoot 'install_windows.ps1'
$repairScript = Join-Path $PSScriptRoot 'repair_windows.ps1'

if ($options.Repair) {
    & $repairScript
    exit $LASTEXITCODE
}

Write-Title
$drives = Get-CandidateDrives
$selectedDrive = $null
$libraryPath = $options.Library

if (-not $libraryPath) {
    if ($options.Drive) {
        $selectedDrive = $drives | Where-Object Drive -ieq $options.Drive | Select-Object -First 1
        if (-not $selectedDrive) { throw "The selected drive is not available: $($options.Drive)" }
        if (-not $selectedDrive.Writable) { throw "The selected drive is not writable from this installer session: $($options.Drive)" }
    } elseif ($options.Silent) {
        $selectedDrive = $drives | Where-Object Writable | Select-Object -First 1
        if (-not $selectedDrive) { throw 'No writable fixed drive was found for unattended installation.' }
    } else {
        $selectedDrive = Select-StorageDrive -Drives $drives
    }
    $libraryPath = Join-Path $selectedDrive.Root 'Fieldora-Library-V5'
}

$manifestPath = Join-Path $libraryPath 'library.json'
$databasePath = Join-Path $libraryPath 'library.sqlite3'
$existingLibrary = (Test-Path -LiteralPath $manifestPath -PathType Leaf) -and (Test-Path -LiteralPath $databasePath -PathType Leaf)

if ($existingLibrary -and -not $options.CreateNew) {
    if (-not $options.Silent -and -not $options.UseExisting) {
        Write-Host ''
        Write-Host "An existing Aperture Library was found at:" -ForegroundColor Green
        Write-Host "  $libraryPath"
        $answer = Read-Host 'Use this existing library? [Y/n]'
        if ($answer -match '^[Nn]') {
            $suffix = Get-Date -Format 'yyyyMMdd-HHmmss'
            $libraryPath = "$libraryPath-$suffix"
            $existingLibrary = $false
        }
    }
} elseif ((Test-Path -LiteralPath $libraryPath) -and -not $existingLibrary) {
    if ($options.UseExisting) { throw "The requested existing library is incomplete: $libraryPath" }
    if (-not $options.Silent) {
        $answer = Read-Host "The folder exists but is not an Aperture Library. Create a new library there? [y/N]"
        if ($answer -notmatch '^[Yy]') { throw 'Installation cancelled by the user.' }
    }
}

$estimatedApp = if ($options.Profile -eq 'FullAI') { 'approximately 10-15 GB including AI dependencies' } else { 'approximately 1-3 GB' }
Write-Host ''
Write-Host 'Installation Summary' -ForegroundColor Cyan
Write-Host '--------------------'
Write-Host ("Application environment: natureai-next")
Write-Host ("Library location:       {0}" -f $libraryPath)
Write-Host ("Library action:         {0}" -f $(if ($existingLibrary) { 'Use existing library' } else { 'Create new Aperture Library' }))
Write-Host ("Install profile:        {0}" -f $options.Profile)
Write-Host ("Torch build:            {0}" -f $options.TorchBuild)
Write-Host ("Estimated application:  {0}" -f $estimatedApp)
Write-Host 'Library storage:        grows with observations, managed photographs, caches, and backups'
Write-Host ''

if (-not $options.Silent) {
    $confirmation = Read-Host 'Continue with installation? [Y/n]'
    if ($confirmation -match '^[Nn]') { Write-Host 'Installation cancelled.'; exit 0 }
}

# One installation transaction: the selected library is passed once to the
# lower-level installer.  That installer creates it (when absent), validates it,
# installs launchers, and only then runs final smoke tests.  There is no second
# environment-destructive registration pass.
& $installScript `
    -InstallProfile $options.Profile `
    -TorchBuild $options.TorchBuild `
    -DefaultLibrary $libraryPath `
    -CreateDefaultLibrary:(-not $existingLibrary) `
    -SkipDeploymentPreflight:$options.SkipDeploymentPreflight
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Aperture installation completed successfully.' -ForegroundColor Green
Write-Host "Library: $libraryPath"
