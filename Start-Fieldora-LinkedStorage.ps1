<#
Start one prepared/enrolled Fieldora linked-storage node against a clean local installation.

The helper consumes the non-secret HANDOFF.json produced by
New-Fieldora-Storage-ServiceTrust.ps1, validates opaque identities and a real host archive
path, then launches the hardened storage-node Compose profile. Storage credentials remain
owned by the host OS; the archive is bind-mounted read-only into the storage container.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($IsWindows) { "D:\FDTEST" } else { Join-Path $HOME "fieldora-server" }),
    [Parameter(Mandatory)][string]$TrustDirectory,
    [Parameter(Mandatory)][string]$StorageRoot,
    [Parameter(Mandatory)][string]$StorageId,
    [Parameter(Mandatory)][string]$DisplayName,
    [Parameter(Mandatory)][string]$RootAlias,
    [string]$Endpoint = "https://fieldora-server:8765",
    [string]$PlatformNetwork = "fieldora_fieldora-network",
    [string]$WorkerId = "storage-preview-1",
    [switch]$RemoteHost
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Assert-Exit([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" }
}

function Assert-Opaque([string]$Name, [string]$Value) {
    $normalized = $Value.Trim()
    if ([string]::IsNullOrWhiteSpace($normalized)) { throw "$Name is required." }
    if ($normalized.Length -gt 200) { throw "$Name is too long." }
    if ($normalized.Contains("/") -or $normalized.Contains("\")) {
        throw "$Name must be an opaque identifier, not a filesystem path."
    }
    if ($normalized -match '^[A-Za-z]:$' -or $normalized -match '^\\\\') {
        throw "$Name must not contain a drive or UNC location."
    }
}

if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required." }
& docker info *> $null
Assert-Exit "Docker is unavailable"
& docker compose version *> $null
Assert-Exit "Docker Compose is unavailable"

Assert-Opaque "StorageId" $StorageId
Assert-Opaque "RootAlias" $RootAlias
Assert-Opaque "WorkerId" $WorkerId

$parsedEndpoint = $null
if (-not [Uri]::TryCreate($Endpoint.Trim(), [UriKind]::Absolute, [ref]$parsedEndpoint)) {
    throw "Endpoint must be an absolute HTTPS origin."
}
if ($parsedEndpoint.Scheme -ne "https" -or -not [string]::IsNullOrEmpty($parsedEndpoint.Query) -or -not [string]::IsNullOrEmpty($parsedEndpoint.Fragment) -or $parsedEndpoint.AbsolutePath -ne "/") {
    throw "Endpoint must be an HTTPS origin without path, query or fragment."
}

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$sourceRoot = Join-Path $installFull "source"
$composeRoot = Join-Path $sourceRoot "deployment\storage-node"
$baseCompose = Join-Path $composeRoot "compose.yaml"
$sameHostCompose = Join-Path $composeRoot "compose.same-host.yaml"
foreach ($required in @($baseCompose)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Storage-node deployment files are missing under $composeRoot. Run the clean installer for this Fieldora ref first."
    }
}
if (-not $RemoteHost -and -not (Test-Path -LiteralPath $sameHostCompose -PathType Leaf)) {
    throw "Same-host storage profile is missing: $sameHostCompose"
}

$trustFull = [IO.Path]::GetFullPath($TrustDirectory)
$handoffPath = Join-Path $trustFull "HANDOFF.json"
if (-not (Test-Path -LiteralPath $handoffPath -PathType Leaf)) {
    throw "Storage trust handoff is missing $handoffPath. Run New-Fieldora-Storage-ServiceTrust.ps1 first."
}
$handoff = Get-Content -LiteralPath $handoffPath -Raw | ConvertFrom-Json
foreach ($required in @("service.crt","service.key","ca-certificate.pem")) {
    if (-not (Test-Path -LiteralPath (Join-Path $trustFull $required) -PathType Leaf)) {
        throw "Storage trust handoff is incomplete: $required"
    }
}
$serviceId = ([string]$handoff.service_id).Trim()
$organizationId = ([string]$handoff.organization_id).Trim()
if ([string]::IsNullOrWhiteSpace($serviceId) -or [string]::IsNullOrWhiteSpace($organizationId)) {
    throw "HANDOFF.json is missing service_id or organization_id."
}
$serviceGuid = [Guid]::Empty
if (-not [Guid]::TryParseExact($serviceId, "D", [ref]$serviceGuid)) {
    throw "HANDOFF.json contains an invalid service_id."
}
if ($organizationId.Contains("/") -or $organizationId.Contains("\")) {
    throw "HANDOFF.json organization_id must not be a filesystem path."
}

$storageFull = [IO.Path]::GetFullPath($StorageRoot)
if (-not (Test-Path -LiteralPath $storageFull -PathType Container)) {
    throw "StorageRoot does not exist or is not a directory: $storageFull"
}
if ($DisplayName.Trim().Length -lt 1 -or $DisplayName.Trim().Length -gt 200) {
    throw "DisplayName must contain 1 to 200 characters."
}

if (-not $RemoteHost) {
    $networkFound = (@(& docker network ls --filter "name=^${PlatformNetwork}$" --format "{{.Name}}") -join "").Trim()
    if ($networkFound -ne $PlatformNetwork) {
        throw "Fieldora private Docker network $PlatformNetwork was not found. Start the clean Fieldora stack first."
    }
}

$env:FIELDORA_STORAGE_ENDPOINT = $parsedEndpoint.GetLeftPart([UriPartial]::Authority)
$env:FIELDORA_STORAGE_SERVICE_ID = $serviceId
$env:FIELDORA_STORAGE_ORGANIZATION = $organizationId
$env:FIELDORA_STORAGE_ID = $StorageId.Trim()
$env:FIELDORA_STORAGE_DISPLAY_NAME = $DisplayName.Trim()
$env:FIELDORA_STORAGE_ROOT_ALIAS = $RootAlias.Trim()
$env:FIELDORA_STORAGE_ROOT = $storageFull
$env:FIELDORA_STORAGE_TRUST_DIR = $trustFull
$env:FIELDORA_STORAGE_WORKER_ID = $WorkerId.Trim()
$env:FIELDORA_PLATFORM_NETWORK = $PlatformNetwork

$composeArgs = @("compose", "-f", $baseCompose)
if (-not $RemoteHost) { $composeArgs += @("-f", $sameHostCompose) }
$composeArgs += @("up", "-d", "--build", "storage-service")

Write-Host "Starting Fieldora linked storage..." -ForegroundColor Cyan
Write-Host "Storage ID  : $($env:FIELDORA_STORAGE_ID)"
Write-Host "Display name: $($env:FIELDORA_STORAGE_DISPLAY_NAME)"
Write-Host "Service ID  : $serviceId"
Write-Host "Organization: $organizationId"
Write-Host "Mode        : $(if ($RemoteHost) { 'remote storage host' } else { 'same-host private network' })"
Write-Host "Archive     : host-owned path mounted read-only into storage service"

& docker @composeArgs
Assert-Exit "Linked storage service failed to start"

$container = "fieldora-storage-service"
$running = (@(& docker inspect --format "{{.State.Status}}" $container 2>$null) -join "").Trim()
if ($running -ne "running") {
    & docker logs $container --tail 200
    throw "Linked storage service is not running."
}
$restartCount = [int]((@(& docker inspect --format "{{.RestartCount}}" $container 2>$null) -join "").Trim())
if ($restartCount -ne 0) {
    & docker logs $container --tail 200
    throw "Linked storage service restarted $restartCount time(s) during startup."
}

Write-Host "Fieldora linked storage: RUNNING" -ForegroundColor Green
Write-Host "Refresh Operator -> Linked archives. The storage service registers the archive over mTLS; host paths and storage credentials remain outside browser metadata." -ForegroundColor Green
