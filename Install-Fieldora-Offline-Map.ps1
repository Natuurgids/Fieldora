<#
Install a verified offline Fieldora map bundle into an existing clean deployment.

The bundle is verified by a one-shot network-isolated Fieldora container. Map files are
never executed and persist outside the application container, mounted read-only into the
server/worker after acceptance.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [Parameter(Mandatory)][string]$BundlePath,
    [ValidateRange(1,1099511627776)][Int64]$MaxBytes = 274877906944,
    [string]$TrustedSigningKey = "",
    [switch]$RequireSignature,
    [switch]$RequireCleanScan
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 or newer is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker was not found." }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running." }

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$bundleFull = [IO.Path]::GetFullPath($BundlePath)
$composePath = Join-Path $installFull "compose.yaml"
$standardOverridePath = Join-Path $installFull "compose.override.yaml"
$modelOverridePath = Join-Path $installFull "compose.models.yaml"
$mapStore = Join-Path $installFull "fieldora-maps"
$overridePath = Join-Path $installFull "compose.maps.yaml"
if (-not (Test-Path -LiteralPath $composePath -PathType Leaf)) { throw "Fieldora compose.yaml was not found under $installFull." }
if (-not (Test-Path -LiteralPath $bundleFull -PathType Container)) { throw "Offline map bundle directory was not found: $bundleFull" }
if (-not (Test-Path -LiteralPath (Join-Path $bundleFull "manifest.json") -PathType Leaf)) { throw "Offline map bundle must contain manifest.json." }
if (($RequireSignature -or $RequireCleanScan) -and [string]::IsNullOrWhiteSpace($TrustedSigningKey)) { throw "-RequireSignature and -RequireCleanScan require -TrustedSigningKey." }
$signingKeyFull = ""
if (-not [string]::IsNullOrWhiteSpace($TrustedSigningKey)) {
    $signingKeyFull = [IO.Path]::GetFullPath($TrustedSigningKey)
    if (-not (Test-Path -LiteralPath $signingKeyFull -PathType Leaf)) { throw "Trusted signing public key was not found: $signingKeyFull" }
}
New-Item -ItemType Directory -Force -Path $mapStore | Out-Null
$image = (@(& docker images --format "{{.Repository}}:{{.Tag}}" "fieldora-v5-rocky:local") -join "").Trim()
if ($image -ne "fieldora-v5-rocky:local") { throw "Fieldora application image fieldora-v5-rocky:local is not installed." }

Write-Host "Verifying and installing offline map bundle..." -ForegroundColor Cyan
$dockerArgs = @(
    "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--user", "0",
    "-v", "${bundleFull}:/bundle:ro", "-v", "${mapStore}:/maps"
)
if ($signingKeyFull) { $dockerArgs += @("-v", "${signingKeyFull}:/trusted-signing-key.pem:ro") }
$dockerArgs += @(
    "fieldora-v5-rocky:local", "python", "-m", "natureai_next.bootstrap.map_bundle_cli",
    "install", "/bundle", "--store", "/maps", "--max-bytes", "$MaxBytes"
)
if ($signingKeyFull) { $dockerArgs += @("--trusted-signing-key", "/trusted-signing-key.pem") }
if ($RequireSignature) { $dockerArgs += "--require-signature" }
if ($RequireCleanScan) { $dockerArgs += "--require-clean-scan" }
& docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw "Offline map verification or installation failed." }

$override = @'
services:
  fieldora-server:
    volumes:
      - ./fieldora-maps:/var/lib/fieldora-maps:ro
    environment:
      FIELDORA_MAP_STORE: /var/lib/fieldora-maps
  fieldora-worker:
    volumes:
      - ./fieldora-maps:/var/lib/fieldora-maps:ro
    environment:
      FIELDORA_MAP_STORE: /var/lib/fieldora-maps
'@
Set-Content -LiteralPath $overridePath -Encoding utf8NoBOM -Value $override
$composeArgs = @("-f", $composePath)
if (Test-Path -LiteralPath $standardOverridePath -PathType Leaf) { $composeArgs += @("-f", $standardOverridePath) }
if (Test-Path -LiteralPath $modelOverridePath -PathType Leaf) { $composeArgs += @("-f", $modelOverridePath) }
$composeArgs += @("-f", $overridePath)
& docker compose @composeArgs config -q
if ($LASTEXITCODE -ne 0) { throw "Fieldora map-store Compose overlay is invalid." }
& docker compose @composeArgs up -d fieldora-server fieldora-worker
if ($LASTEXITCODE -ne 0) { throw "Fieldora services could not be recreated with the offline map store." }
Write-Host "Offline map installed and map store mounted read-only." -ForegroundColor Green
if ($RequireSignature -or $RequireCleanScan) { Write-Host "Manifest signature: required and verified against the supplied Ed25519 public key." -ForegroundColor Green }
if ($RequireCleanScan) { Write-Host "Malware scan: signed clean attestation required and verified." -ForegroundColor Green }
Write-Host "Browser/API map metadata uses opaque artifact IDs; host paths are not exposed."
