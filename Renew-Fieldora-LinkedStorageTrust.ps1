<#
Renew one enrolled Fieldora linked-storage service certificate without WAN access.

Run this helper on the trusted Fieldora host on a regular schedule (for example daily).
It uses only the clean installation's constrained issuer Docker volume, the local governance
DSN, and the storage trust handoff directory. The offline root CA private key is not mounted.
The certificate renewer also updates the durable Operator service certificate metadata.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($IsWindows) { "D:\FDTEST" } else { Join-Path $HOME "fieldora-server" }),
    [Parameter(Mandatory)][string]$TrustDirectory,
    [ValidateRange(1,720)][int]$LifetimeHours = 168,
    [ValidateRange(1,720)][int]$RenewBeforeHours = 48,
    [switch]$ForceRenewal
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Assert-Exit([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" }
}

function Docker-Output {
    param([Parameter(Mandatory)][scriptblock]$Command)
    return (@(& $Command) -join "`n").Trim()
}

if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required." }
if ($RenewBeforeHours -gt $LifetimeHours) { throw "RenewBeforeHours must not exceed LifetimeHours." }
& docker info *> $null
Assert-Exit "Docker is unavailable"

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$trustFull = [IO.Path]::GetFullPath($TrustDirectory)
$handoffPath = Join-Path $trustFull "HANDOFF.json"
if (-not (Test-Path -LiteralPath $handoffPath -PathType Leaf)) {
    throw "Storage trust handoff is missing $handoffPath."
}
$handoff = Get-Content -LiteralPath $handoffPath -Raw | ConvertFrom-Json
$serviceId = ([string]$handoff.service_id).Trim()
$organizationId = ([string]$handoff.organization_id).Trim()
$serviceGuid = [Guid]::Empty
if (-not [Guid]::TryParseExact($serviceId, "D", [ref]$serviceGuid)) {
    throw "HANDOFF.json contains an invalid service_id."
}
if ([string]::IsNullOrWhiteSpace($organizationId) -or $organizationId.Contains("/") -or $organizationId.Contains("\")) {
    throw "HANDOFF.json contains an invalid organization_id."
}
foreach ($required in @("service.crt","service.key","ca-certificate.pem")) {
    if (-not (Test-Path -LiteralPath (Join-Path $trustFull $required) -PathType Leaf)) {
        throw "Storage trust handoff is incomplete: $required"
    }
}

$image = "fieldora-v5-rocky:local"
$imageFound = (@(& docker images --format "{{.Repository}}:{{.Tag}}") -join "`n") -split "`n" | Where-Object { $_ -eq $image }
if (-not $imageFound) { throw "Fieldora runtime image $image is missing." }
$issuerFound = (@(& docker volume ls --filter "name=^fieldora-issuer-authority$" --format "{{.Name}}") -join "").Trim()
if ($issuerFound -ne "fieldora-issuer-authority") {
    throw "Constrained Fieldora issuer volume is missing. Run the clean installer first."
}

$governanceDsn = Join-Path $installFull "secrets\fieldora-governance-dsn"
if (-not (Test-Path -LiteralPath $governanceDsn -PathType Leaf)) {
    throw "Fieldora governance DSN is missing under the clean installation."
}

# Fail closed if the online issuer volume ever contains the offline root private key.
& docker run --rm --user 0 -v fieldora-issuer-authority:/authority:ro $image sh -lc "test ! -e /authority/ca-private.pem && test -f /authority/ca-certificate.pem && test -f /authority/issuer-certificate.pem && test -f /authority/issuer-private.pem"
Assert-Exit "Constrained issuer boundary is invalid"

$fieldoraUid = [int](Docker-Output { docker run --rm $image id -u fieldora })
Assert-Exit "Unable to determine Fieldora storage uid"
$fieldoraGid = [int](Docker-Output { docker run --rm $image id -g fieldora })
Assert-Exit "Unable to determine Fieldora storage gid"

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "fieldora-storage-renew-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
try {
    $config = @{
        services = @(
            @{
                service_id = $serviceId
                organization_id = $organizationId
                common_name = "fieldora-linked-storage"
                certificate = "/target/service.crt"
                private_key = "/target/service.key"
                dns_names = @()
                ip_addresses = @()
                uid = $fieldoraUid
                gid = $fieldoraGid
            }
        )
    }
    $configPath = Join-Path $tempRoot "renewal.json"
    $config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding utf8NoBOM
    $window = if ($ForceRenewal) { $LifetimeHours } else { $RenewBeforeHours }

    Write-Host "Checking linked-storage certificate renewal for $serviceId..." -ForegroundColor Cyan
    & docker run --rm --user 0 `
        -v fieldora-issuer-authority:/authority:ro `
        -v "${trustFull}:/target" `
        -v "${governanceDsn}:/run/secrets/fieldora-governance-dsn:ro" `
        -v "${configPath}:/run/fieldora-renewal/storage.json:ro" `
        $image `
        fieldora-certificate-renewer `
        --authority-root /authority `
        --postgres-dsn-file /run/secrets/fieldora-governance-dsn `
        --config /run/fieldora-renewal/storage.json `
        --interval-seconds 3600 `
        --renew-before-hours $window `
        --lifetime-hours $LifetimeHours `
        --once
    Assert-Exit "Linked-storage certificate renewal failed"

    $inspection = Docker-Output {
        docker run --rm --user 0 `
            -v fieldora-issuer-authority:/authority:ro `
            -v "${trustFull}:/target:ro" `
            $image `
            fieldora-service-trust --root /authority inspect --certificate /target/service.crt
    }
    Assert-Exit "Unable to inspect renewed linked-storage certificate"
    $certificate = $inspection | ConvertFrom-Json
    if ($certificate.service_id -ne $serviceId -or $certificate.organization_id -ne $organizationId) {
        throw "Renewed certificate identity does not match the durable linked-storage identity."
    }
    Write-Host "Linked-storage certificate: CURRENT" -ForegroundColor Green
    Write-Host "Service ID : $serviceId"
    Write-Host "Serial     : $($certificate.serial_number)"
    Write-Host "Expires UTC: $($certificate.not_after_utc)"
    Write-Host "The running storage agent reloads certificate files for subsequent mTLS requests; no WAN or Bastion is involved." -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
