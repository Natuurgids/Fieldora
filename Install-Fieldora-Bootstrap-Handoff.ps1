<#
Configure temporary installer/admin credential handoff cleanup for an existing Fieldora container installation.
Works with PowerShell 7 on Windows and Linux. The cleaner has no network or Fieldora database/trust access.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [ValidateRange(1,90)][int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 or newer is required."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker was not found. Install Docker/Podman-compatible Docker CLI first."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "The container engine is not available." }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose is unavailable." }

$root = [IO.Path]::GetFullPath($InstallRoot)
$baseCompose = Join-Path $root "compose.yaml"
if (-not (Test-Path -LiteralPath $baseCompose)) {
    throw "Fieldora compose.yaml was not found at $baseCompose"
}

$handoff = Join-Path $root "bootstrap-handoff"
New-Item -ItemType Directory -Force -Path $handoff | Out-Null

$legacyCredentials = Join-Path $root "ADMIN-CREDENTIALS.txt"
$credentials = Join-Path $handoff "ADMIN-CREDENTIALS.txt"
if (Test-Path -LiteralPath $legacyCredentials) {
    Move-Item -LiteralPath $legacyCredentials -Destination $credentials -Force
}
if (-not (Test-Path -LiteralPath $credentials)) {
    throw "ADMIN-CREDENTIALS.txt was not found in the installation root or bootstrap-handoff directory."
}

$expiresAt = [DateTimeOffset]::UtcNow.AddDays($RetentionDays)
Set-Content -LiteralPath (Join-Path $handoff "EXPIRES-AT-EPOCH") -Encoding ascii -NoNewline -Value $expiresAt.ToUnixTimeSeconds()
Set-Content -LiteralPath (Join-Path $handoff "README.txt") -Encoding utf8NoBOM -Value @"
Fieldora bootstrap credential handoff
====================================
ADMIN-CREDENTIALS.txt is temporary installer handoff material.
It is scheduled for automatic deletion after $RetentionDays day(s), at $($expiresAt.ToString('u')).
Deleting this file does not delete or disable the administrator account.
Copy the credential into the organisation's approved password manager before expiry.
"@

$overridePath = Join-Path $root "compose.bootstrap-handoff.yaml"
$override = @'
services:
  fieldora-bootstrap-handoff-cleaner:
    image: fieldora-v5-rocky:local
    container_name: fieldora-bootstrap-handoff-cleaner
    restart: unless-stopped
    network_mode: none
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    command:
      - python3.11
      - -m
      - natureai_next.bootstrap.bootstrap_handoff_cleanup_cli
      - --directory
      - /run/fieldora-bootstrap-handoff
      - --interval-seconds
      - "3600"
    volumes:
      - ./bootstrap-handoff:/run/fieldora-bootstrap-handoff
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=8m
'@
Set-Content -LiteralPath $overridePath -Encoding utf8NoBOM -Value $override

Push-Location $root
try {
    & docker compose -f compose.yaml -f compose.bootstrap-handoff.yaml config -q
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap handoff Compose configuration is invalid." }

    & docker compose -f compose.yaml -f compose.bootstrap-handoff.yaml up -d fieldora-bootstrap-handoff-cleaner
    if ($LASTEXITCODE -ne 0) { throw "Unable to start the bootstrap handoff cleaner." }

    $state = (@(& docker inspect --format "{{.State.Status}}" fieldora-bootstrap-handoff-cleaner 2>$null) -join "").Trim()
    if ($state -ne "running") { throw "Bootstrap handoff cleaner is not running (state: $state)." }
finally {
    Pop-Location
}

Write-Host "Fieldora bootstrap credential handoff: CONFIGURED" -ForegroundColor Green
Write-Host "Credentials: $credentials"
Write-Host "Automatic plaintext cleanup: $($expiresAt.ToString('u'))"
Write-Host "Cleaner network: none"
