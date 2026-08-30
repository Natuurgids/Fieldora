<#
Create the mTLS trust handoff for one prepared Fieldora linked-storage service ID.

This helper is intentionally run on the trusted Fieldora host. It uses the existing
installation-local constrained service issuer through a short-lived container, writes only
the storage service certificate/private key plus the public CA certificate to the handoff
directory, and never exposes key material to the browser or mounts the offline root CA key.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($IsWindows) { "D:\FDTEST" } else { Join-Path $HOME "fieldora-server" }),
    [Parameter(Mandatory)][string]$ServiceId,
    [Parameter(Mandatory)][string]$Organization,
    [ValidateRange(1,720)][int]$CertificateHours = 168,
    [string]$OutputRoot = "",
    [switch]$Force
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
& docker info *> $null
Assert-Exit "Docker is unavailable"

$serviceGuid = [Guid]::Empty
if (-not [Guid]::TryParseExact($ServiceId.Trim(), "D", [ref]$serviceGuid)) {
    throw "ServiceId must be the canonical UUID prepared by Fieldora Operator."
}
$canonicalServiceId = $serviceGuid.ToString("D").ToLowerInvariant()
if ($ServiceId.Trim().ToLowerInvariant() -ne $canonicalServiceId) {
    throw "ServiceId must use canonical UUID formatting."
}
$organizationId = $Organization.Trim()
if ([string]::IsNullOrWhiteSpace($organizationId)) { throw "Organization is required." }
if ($organizationId.Contains("/") -or $organizationId.Contains("\")) {
    throw "Organization must be the Fieldora organization identifier, not a path."
}

$installFull = [IO.Path]::GetFullPath($InstallRoot)
$sourceRoot = Join-Path $installFull "source"
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "pyproject.toml"))) {
    throw "Fieldora source is missing under $sourceRoot. Run the clean installer first."
}

$image = "fieldora-v5-rocky:local"
$imageFound = (@(& docker images --format "{{.Repository}}:{{.Tag}}") -join "`n") -split "`n" | Where-Object { $_ -eq $image }
if (-not $imageFound) { throw "Fieldora runtime image $image is missing. Run the clean installer first." }

$issuerVolume = "fieldora-issuer-authority"
$volumeFound = (@(& docker volume ls --filter "name=^${issuerVolume}$" --format "{{.Name}}") -join "").Trim()
if ($volumeFound -ne $issuerVolume) {
    throw "Constrained Fieldora issuer volume $issuerVolume is missing. Run the clean installer first."
}
& docker run --rm --user 0 -v "${issuerVolume}:/authority:ro" $image sh -lc "test -f /authority/ca-certificate.pem && test -f /authority/issuer-certificate.pem && test -f /authority/issuer-private.pem && test ! -e /authority/ca-private.pem"
Assert-Exit "Constrained issuer authority is incomplete or contains the offline root CA private key"

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $installFull (Join-Path "linked-storage-trust" $canonicalServiceId)
}
$outputFull = [IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $outputFull | Out-Null
$certificatePath = Join-Path $outputFull "service.crt"
$privateKeyPath = Join-Path $outputFull "service.key"
$caPath = Join-Path $outputFull "ca-certificate.pem"
if (-not $Force -and ((Test-Path $certificatePath) -or (Test-Path $privateKeyPath))) {
    throw "Storage service trust already exists at $outputFull. Use -Force only for an intentional certificate/key replacement."
}
Remove-Item -LiteralPath $certificatePath,$privateKeyPath,$caPath -Force -ErrorAction SilentlyContinue

Write-Host "Issuing mTLS certificate for linked-storage service $canonicalServiceId..." -ForegroundColor Cyan
$issuedJson = Docker-Output {
    docker run --rm --user 0 `
        -v "${issuerVolume}:/authority:ro" `
        -v "${outputFull}:/output" `
        $image `
        fieldora-service-trust --root /authority issue `
        --service-id $canonicalServiceId `
        --organization $organizationId `
        --common-name fieldora-linked-storage `
        --certificate /output/service.crt `
        --private-key /output/service.key `
        --hours $CertificateHours `
        --new-private-key
}
Assert-Exit "Storage service certificate issuance failed"
$issued = $issuedJson | ConvertFrom-Json
if ($issued.service_id -ne $canonicalServiceId -or $issued.organization_id -ne $organizationId) {
    throw "Issued certificate identity does not match the requested Fieldora service identity."
}

& docker run --rm --user 0 -v "${issuerVolume}:/authority:ro" -v "${outputFull}:/output" $image sh -lc "cp /authority/ca-certificate.pem /output/ca-certificate.pem"
Assert-Exit "Unable to copy the public Fieldora CA certificate into the storage handoff"
foreach ($required in @($certificatePath,$privateKeyPath,$caPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Storage trust handoff is incomplete: $required" }
}

# The storage image runs as the Fieldora service user. Normalize Linux bind-mount
# ownership/modes in a one-shot root container; Docker Desktop safely ignores the
# ownership distinction where the host filesystem does not implement Linux uid/gid.
$fieldoraUid = [int](Docker-Output { docker run --rm $image id -u fieldora })
Assert-Exit "Unable to determine Fieldora storage uid"
$fieldoraGid = [int](Docker-Output { docker run --rm $image id -g fieldora })
Assert-Exit "Unable to determine Fieldora storage gid"
& docker run --rm --user 0 -v "${outputFull}:/target" $image sh -lc "chown ${fieldoraUid}:${fieldoraGid} /target/service.crt /target/service.key /target/ca-certificate.pem && chmod 644 /target/service.crt /target/ca-certificate.pem && chmod 600 /target/service.key"
Assert-Exit "Unable to normalize storage service trust permissions"

$expiry = [DateTimeOffset]::FromUnixTimeSeconds([int64]$issued.not_after_epoch).UtcDateTime
$handoff = [ordered]@{
    service_id = $canonicalServiceId
    organization_id = $organizationId
    certificate_serial = [string]$issued.serial_number
    certificate_not_after_epoch = [int64]$issued.not_after_epoch
    certificate_expiry_date = $expiry.ToString("yyyy-MM-dd")
    trust_directory = $outputFull
    browser_safe_fields = @("service_id", "organization_id", "certificate_serial", "certificate_expiry_date")
    private_key_content_recorded = $false
    offline_root_ca_private_key_mounted = $false
}
$handoffPath = Join-Path $outputFull "HANDOFF.json"
$handoff | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Write-Host "Storage service trust handoff: READY" -ForegroundColor Green
Write-Host "Service ID        : $canonicalServiceId"
Write-Host "Organization      : $organizationId"
Write-Host "Certificate serial: $($handoff.certificate_serial)"
Write-Host "Certificate expiry: $($handoff.certificate_expiry_date)"
Write-Host "Trust directory   : $outputFull"
Write-Host ""
Write-Host "Enter only Service ID, certificate serial and expiry in Operator. Do not paste service.key or CA material into the browser." -ForegroundColor Yellow
Write-Output ($handoff | ConvertTo-Json -Depth 3 -Compress)
