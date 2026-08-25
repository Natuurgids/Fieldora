<#
Install an approved Fieldora AI-model or offline-map bundle from local/removable media.

This is the organization-admin high-assurance media path. It never downloads package
content. The bundle and trusted Ed25519 public key are supplied locally (for example from
a USB stick), then the existing Fieldora trusted-side one-shot installer independently
verifies the signed manifest, clean malware-scan attestation, file sizes and SHA-256
content before changing the persistent model/map store.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [Parameter(Mandatory)][string]$BundlePath,
    [Parameter(Mandatory)][string]$TrustedSigningKey,
    [ValidateSet("auto","model","map")][string]$PackageClass = "auto"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 or newer is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required." }

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$bundleFull = [IO.Path]::GetFullPath($BundlePath)
$keyFull = [IO.Path]::GetFullPath($TrustedSigningKey)
if (-not (Test-Path -LiteralPath $bundleFull -PathType Container)) {
    throw "Local media bundle directory was not found: $bundleFull"
}
if (-not (Test-Path -LiteralPath $keyFull -PathType Leaf)) {
    throw "Trusted signing public key was not found: $keyFull"
}
$manifestPath = Join-Path $bundleFull "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Local media bundle must contain manifest.json."
}
try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
}
catch {
    throw "Local media manifest.json is invalid JSON. $($_.Exception.Message)"
}

$detected = ""
if ([string]$manifest.package_class -eq "map" -or -not [string]::IsNullOrWhiteSpace([string]$manifest.map_id)) {
    $detected = "map"
}
elseif (-not [string]::IsNullOrWhiteSpace([string]$manifest.model_id)) {
    $detected = "model"
}
else {
    throw "Local media manifest does not identify a supported Fieldora model or map package."
}
if ($PackageClass -ne "auto" -and $PackageClass -ne $detected) {
    throw "Requested package class '$PackageClass' does not match manifest class '$detected'."
}

$sourceRoot = Join-Path $installFull "source"
$installerName = if ($detected -eq "map") { "Install-Fieldora-Offline-Map.ps1" } else { "Install-Fieldora-Offline-Model.ps1" }
$installer = Join-Path $sourceRoot $installerName
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Installed Fieldora source does not contain $installerName. Upgrade Fieldora before using removable-media import."
}

Write-Host "Installing approved $detected package from local/removable media..." -ForegroundColor Cyan
Write-Host "Transport: local media only; no package download is performed." -ForegroundColor Cyan
& $installer `
    -InstallRoot $installFull `
    -BundlePath $bundleFull `
    -TrustedSigningKey $keyFull `
    -RequireSignature `
    -RequireCleanScan
if ($LASTEXITCODE -ne 0) {
    throw "Fieldora rejected the local-media $detected package (exit code $LASTEXITCODE)."
}

Write-Host "Fieldora local-media $detected installation: VERIFIED" -ForegroundColor Green
Write-Host "Signed manifest, clean-scan attestation and payload digests were required." -ForegroundColor Green
