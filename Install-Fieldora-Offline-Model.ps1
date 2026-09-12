<#
Install a verified offline Fieldora model bundle into an existing clean deployment.

Works with PowerShell 7 on Windows or Linux. The model bundle is processed by a
one-shot container with no network access. Model files persist outside the
application container and are mounted read-only into the API and worker.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [Parameter(Mandatory)][string]$BundlePath,
    [ValidateRange(1,1099511627776)][Int64]$MaxBytes = 68719476736,
    [string]$TrustedSigningKey = "",
    [switch]$RequireSignature,
    [switch]$RequireCleanScan
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running." }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose is unavailable." }

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$bundleFull = [IO.Path]::GetFullPath($BundlePath)
$composePath = Join-Path $installFull "compose.yaml"
$standardOverridePath = Join-Path $installFull "compose.override.yaml"
$modelStore = Join-Path $installFull "fieldora-models"
$overridePath = Join-Path $installFull "compose.models.yaml"

if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) {
    throw "Fieldora compose.yaml was not found under $installFull."
}
if (-not (Test-Path -LiteralPath $bundleFull -PathType Container)) {
    throw "Offline model bundle directory was not found: $bundleFull"
}
if (-not (Test-Path -LiteralPath (Join-Path $bundleFull "manifest.json") -PathType Leaf)) {
    throw "Offline model bundle must contain manifest.json."
}
if (($RequireSignature -or $RequireCleanScan) -and [string]::IsNullOrWhiteSpace($TrustedSigningKey)) {
    throw "-RequireSignature and -RequireCleanScan require -TrustedSigningKey."
}
$signingKeyFull = ""
if (-not [string]::IsNullOrWhiteSpace($TrustedSigningKey)) {
    $signingKeyFull = [IO.Path]::GetFullPath($TrustedSigningKey)
    if (-not (Test-Path -LiteralPath $signingKeyFull -PathType Leaf)) {
        throw "Trusted signing public key was not found: $signingKeyFull"
    }
}
New-Item -ItemType Directory -Force -Path $modelStore | Out-Null

$image = (@(& docker images --format "{{.Repository}}:{{.Tag}}" "fieldora-v5-rocky:local") -join "").Trim()
if ($image -ne "fieldora-v5-rocky:local") {
    throw "Fieldora application image fieldora-v5-rocky:local is not installed."
}

Write-Host "Verifying and installing offline model bundle..." -ForegroundColor Cyan
$dockerArgs = @(
    "run", "--rm",
    "--network", "none",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--user", "0",
    "-v", "${bundleFull}:/bundle:ro",
    "-v", "${modelStore}:/models"
)
if ($signingKeyFull) {
    $dockerArgs += @("-v", "${signingKeyFull}:/trusted-signing-key.pem:ro")
}
$dockerArgs += @(
    "fieldora-v5-rocky:local",
    "fieldora-model-bundle", "install", "/bundle",
    "--store", "/models",
    "--max-bytes", "$MaxBytes"
)
if ($signingKeyFull) {
    $dockerArgs += @("--trusted-signing-key", "/trusted-signing-key.pem")
}
if ($RequireSignature) {
    $dockerArgs += "--require-signature"
}
if ($RequireCleanScan) {
    $dockerArgs += "--require-clean-scan"
}
& docker @dockerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Offline model verification or installation failed."
}

$override = @'
services:
  fieldora-server:
    volumes:
      - ./fieldora-models:/var/lib/fieldora-models:ro
    environment:
      FIELDORA_MODEL_STORE: /var/lib/fieldora-models
  fieldora-worker:
    volumes:
      - ./fieldora-models:/var/lib/fieldora-models:ro
    environment:
      FIELDORA_MODEL_STORE: /var/lib/fieldora-models
'@
Set-Content -LiteralPath $overridePath -Encoding utf8NoBOM -Value $override

# Preserve the clean install's standard override (for example the internal mTLS
# storage-service listener) when applying the model-store overlay. Explicit -f
# arguments otherwise suppress Compose's automatic compose.override.yaml loading.
$composeArgs = @("-f", $composePath)
if (Test-Path -LiteralPath $standardOverridePath -PathType Leaf) {
    $composeArgs += @("-f", $standardOverridePath)
}
$composeArgs += @("-f", $overridePath)

Write-Host "Validating model-store Compose overlay with existing Fieldora overrides..." -ForegroundColor Cyan
& docker compose @composeArgs config -q
if ($LASTEXITCODE -ne 0) {
    throw "Fieldora model-store Compose overlay is invalid or conflicts with the existing deployment override."
}

Write-Host "Applying persistent read-only model-store mount..." -ForegroundColor Cyan
& docker compose @composeArgs up -d fieldora-server fieldora-worker
if ($LASTEXITCODE -ne 0) {
    throw "Fieldora services could not be recreated with the offline model store."
}

Write-Host ""
Write-Host "Offline model installed and model store mounted read-only." -ForegroundColor Green
if ($RequireSignature -or $RequireCleanScan) {
    Write-Host "Manifest signature: required and verified against the supplied Ed25519 public key." -ForegroundColor Green
}
if ($RequireCleanScan) {
    Write-Host "Malware scan: signed clean attestation required and verified." -ForegroundColor Green
}
Write-Host "Model registry metadata uses opaque artifact storage IDs; host paths are not browser metadata."
Write-Host "For future docker compose operations, include compose.models.yaml so the model mount remains part of the desired state."
