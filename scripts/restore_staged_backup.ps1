param(
    [Parameter(Mandatory=$true)][string]$StagingDirectory
)
$ErrorActionPreference = "Stop"
$requestPath = Join-Path $StagingDirectory "pending-restore.json"
if (-not (Test-Path $requestPath)) { throw "No pending restore request was found." }
if (Get-Process -Name "Aperture","python","pythonw" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "Aperture*" }) {
    throw "Close Aperture before restoring a library."
}
$request = Get-Content $requestPath -Raw | ConvertFrom-Json
if ($request.format -ne "natureai-next.pending-restore" -or $request.format_version -ne 1) { throw "Unsupported restore request." }
$staged = [System.IO.Path]::GetFullPath($request.staged_database)
$target = [System.IO.Path]::GetFullPath($request.target_database)
$emergency = [System.IO.Path]::GetFullPath($request.emergency_backup)
if (-not (Test-Path $staged)) { throw "The staged backup is missing." }
$actual = (Get-FileHash -Algorithm SHA256 $staged).Hash.ToLowerInvariant()
if ($actual -ne $request.sha256.ToLowerInvariant()) { throw "The staged backup checksum is invalid." }
if (-not (Test-Path $emergency)) { throw "The emergency pre-restore backup is missing." }
$rollback = "$target.pre-restore-rollback"
if (Test-Path $rollback) { Remove-Item $rollback -Force }
Copy-Item $target $rollback -Force
try {
    Copy-Item $staged $target -Force
    Remove-Item $requestPath -Force
    Write-Host "Restore completed. Start Aperture and run Health Check."
} catch {
    Copy-Item $rollback $target -Force
    throw
}
