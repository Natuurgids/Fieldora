param(
    [Parameter(Mandatory=$false)][string]$ApplicationDirectory = (Resolve-Path "$PSScriptRoot\..").Path,
    [Parameter(Mandatory=$false)][string]$StagingDirectory
)
$ErrorActionPreference = "Stop"
if (-not $StagingDirectory) { throw "Provide -StagingDirectory pointing to the Aperture library updates\staging folder." }
$request = Join-Path $StagingDirectory "pending-update.json"
if (-not (Test-Path $request)) { throw "No pending-update.json was found." }
$pending = Get-Content $request -Raw | ConvertFrom-Json
$package = Join-Path $StagingDirectory $pending.package
if (-not (Test-Path $package)) { throw "The staged package is missing." }
$actual = (Get-FileHash $package -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $pending.sha256.ToLowerInvariant()) { throw "The staged package checksum is invalid." }
$process = Get-Process | Where-Object { $_.ProcessName -match 'natureai|aperture' }
if ($process) { throw "Close Aperture before installing the staged update." }
$rollback = "$ApplicationDirectory.rollback"
if (Test-Path $rollback) { Remove-Item $rollback -Recurse -Force }
Copy-Item $ApplicationDirectory $rollback -Recurse
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("Aperture-Update-" + [guid]::NewGuid())
New-Item $temp -ItemType Directory | Out-Null
try {
    Expand-Archive $package -DestinationPath $temp -Force
    Get-ChildItem $ApplicationDirectory -Force | Where-Object { $_.Name -notin @('.git') } | Remove-Item -Recurse -Force
    Copy-Item (Join-Path $temp '*') $ApplicationDirectory -Recurse -Force
    $pending.status = 'installed'
    $pending.installed_at_utc = [DateTime]::UtcNow.ToString('o')
    $pending | ConvertTo-Json | Set-Content $request -Encoding UTF8
    Write-Host "Aperture $($pending.version) installed. Rollback copy: $rollback"
} catch {
    Get-ChildItem $ApplicationDirectory -Force | Remove-Item -Recurse -Force
    Copy-Item (Join-Path $rollback '*') $ApplicationDirectory -Recurse -Force
    throw "Update failed and the prior application files were restored. $($_.Exception.Message)"
} finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}
