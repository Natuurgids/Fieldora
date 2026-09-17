[CmdletBinding()]
param(
    [string]$OutputDirectory = 'dist-installer-linux'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsLinux) { throw 'Build this review bundle on Linux with PowerShell 7.' }

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$OutputRoot = Join-Path $RepositoryRoot $OutputDirectory
Remove-Item -LiteralPath $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$files = @(
    'Install-Fieldora-Clean-Linux.ps1',
    'Install-Fieldora-Clean.ps1',
    'Install-Fieldora-Bootstrap-Handoff.ps1',
    'Install-Fieldora-Offline-Model.ps1'
)
foreach ($relative in $files) {
    $source = Join-Path $RepositoryRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing Linux installer component: $relative" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $OutputRoot $relative) -Force
}

$manifest = foreach ($relative in $files) {
    $path = Join-Path $OutputRoot $relative
    [pscustomobject]@{
        file = $relative
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot 'SHA256SUMS.json') -Encoding utf8NoBOM

$archive = Join-Path $RepositoryRoot 'Fieldora-Linux-Installer-Review.zip'
Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $OutputRoot '*') -DestinationPath $archive -CompressionLevel Optimal
$archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$archiveHash  $(Split-Path -Leaf $archive)" | Set-Content -LiteralPath "$archive.sha256" -Encoding ascii
Write-Host "Fieldora Linux review bundle: $archive" -ForegroundColor Green
Write-Host "SHA-256: $archiveHash"