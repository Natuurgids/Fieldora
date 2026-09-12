<#
Linux entry point for the Fieldora clean Docker installer.

This wrapper preserves the repository-controlled clean deployment architecture used by
Windows while adapting only host-specific Docker checks, host certificate trust guidance,
and curl smoke testing for PowerShell 7 on Linux. It also configures the same temporary
credential handoff, internal storage-service mTLS listener, and optional verified offline
model installation.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $HOME "fieldora-server"),
    [string]$FieldoraRef = "feature/versioned-facility-floorplans",
    [string]$AdminUsername = "admin",
    [string]$AdminName = "Administrator",
    [string]$Organization = "local",
    [string]$AdminPassword = "",
    [ValidateRange(1,90)][int]$CredentialHandoffRetentionDays = 7,
    [string]$OfflineModelBundle = "",
    [string]$OfflineModelTrustedSigningKey = "",
    [switch]$RequireOfflineModelSignature,
    [switch]$RequireOfflineModelCleanScan
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 is required. Start pwsh and run this installer again."
}
if (-not $IsLinux) { throw "This entry point is for Linux hosts." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "docker was not found." }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "The Docker Linux engine is not running or is not accessible to this user." }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose is unavailable." }
if (-not (Get-Command curl -ErrorAction SilentlyContinue)) { throw "curl is required for TLS smoke testing." }
if (($RequireOfflineModelSignature -or $RequireOfflineModelCleanScan) -and [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
    throw "Offline model verification switches require -OfflineModelBundle."
}

$installFull = [IO.Path]::GetFullPath($InstallRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$currentFull = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
$separator = [IO.Path]::DirectorySeparatorChar
if ($currentFull -eq $installFull -or $currentFull.StartsWith($installFull + $separator, [StringComparison]::Ordinal)) {
    throw "Do not run this installer from inside $InstallRoot. Choose a shell directory outside the destructive installation root."
}

$encodedRef = [Uri]::EscapeDataString($FieldoraRef)
$baseUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef"
if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') {
    $baseUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef"
}
$coreUrl = "$baseUrl/Install-Fieldora-Clean.ps1"
$handoffUrl = "$baseUrl/Install-Fieldora-Bootstrap-Handoff.ps1"
$modelInstallerUrl = "$baseUrl/Install-Fieldora-Offline-Model.ps1"
$tempCore = Join-Path ([IO.Path]::GetTempPath()) "Install-Fieldora-Clean-Linux-Core-$([Guid]::NewGuid().ToString('N')).ps1"
$tempHandoff = Join-Path ([IO.Path]::GetTempPath()) "Install-Fieldora-Bootstrap-Handoff-$([Guid]::NewGuid().ToString('N')).ps1"
$tempModelInstaller = Join-Path ([IO.Path]::GetTempPath()) "Install-Fieldora-Offline-Model-$([Guid]::NewGuid().ToString('N')).ps1"

function Require-Marker([string]$Text, [string]$Marker) {
    if (-not $Text.Contains($Marker)) {
        throw "The clean installer changed and the Linux compatibility marker is missing: $Marker"
    }
}

try {
    Write-Host "Downloading repository clean installer from $FieldoraRef..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $coreUrl -OutFile $tempCore -UseBasicParsing
    $core = Get-Content -LiteralPath $tempCore -Raw

    $windowsDocker = @'
Step "Checking Docker Desktop"
if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw "docker.exe was not found." }
try { & docker info *> $null } catch { }
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop Linux engine is not running." }
$dockerOs = (@(& docker info --format '{{.OSType}}') -join "").Trim()
Assert-Exit "Unable to inspect Docker"
if ($dockerOs -ne "linux") { throw "Docker Desktop must use Linux containers." }
'@
    $linuxDocker = @'
Step "Checking Docker Engine"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "docker was not found." }
try { & docker info *> $null } catch { }
if ($LASTEXITCODE -ne 0) { throw "Docker Linux engine is not running or is not accessible." }
$dockerOs = (@(& docker info --format '{{.OSType}}') -join "").Trim()
Assert-Exit "Unable to inspect Docker"
if ($dockerOs -ne "linux") { throw "Fieldora requires Linux containers." }
'@
    Require-Marker $core $windowsDocker
    $core = $core.Replace($windowsDocker, $linuxDocker)
    $core = $core.Replace('--node docker-desktop', '--node linux-docker')

    $trustStartMarker = '    Step "Trusting the local Fieldora HTTPS certificate for the current Windows user"'
    $trustEndMarker = '    Step "Starting complete Fieldora stack"'
    Require-Marker $core $trustStartMarker
    Require-Marker $core $trustEndMarker
    $trustStart = $core.IndexOf($trustStartMarker, [StringComparison]::Ordinal)
    $trustEnd = $core.IndexOf($trustEndMarker, $trustStart, [StringComparison]::Ordinal)
    if ($trustEnd -le $trustStart) { throw "Unable to isolate Windows host-trust block." }
    $linuxTrust = @'
    Step "Preparing Linux host trust guidance"
    Write-Host "Fieldora uses its private CA for HTTPS. The installer will verify TLS with that CA explicitly." -ForegroundColor Green
    Write-Host "To trust Fieldora in a host browser, add service-trust/ca-certificate.pem to your distribution/browser trust store after installation."

'@
    $core = $core.Substring(0, $trustStart) + $linuxTrust + $core.Substring($trustEnd)

    $curlStartMarker = '    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue'
    $curlEndMarker = '    $servicesJson = Docker-Output'
    Require-Marker $core $curlStartMarker
    Require-Marker $core $curlEndMarker
    $curlStart = $core.IndexOf($curlStartMarker, [StringComparison]::Ordinal)
    $curlEnd = $core.IndexOf($curlEndMarker, $curlStart, [StringComparison]::Ordinal)
    if ($curlEnd -le $curlStart) { throw "Unable to isolate Windows TLS smoke-test block." }
    $linuxCurl = @'
    $curl = Get-Command curl -ErrorAction SilentlyContinue
    if (-not $curl) { throw "curl is required for TLS smoke testing on Linux." }
    $curlBinary = $curl.Source
    $caFile = Join-Path $TrustRoot "ca-certificate.pem"
    $curlTrust = @("--fail","--silent","--show-error","--cacert",$caFile)
    & $curlBinary @curlTrust https://127.0.0.1:8765/ -o /dev/null
    Assert-Exit "Fieldora HTTPS root test failed after live certificate renewal"
    $live = (& $curlBinary @curlTrust https://127.0.0.1:8765/health/live) | ConvertFrom-Json
    Assert-Exit "Fieldora liveness test failed"
    $ready = (& $curlBinary @curlTrust https://127.0.0.1:8765/health/ready) | ConvertFrom-Json
    Assert-Exit "Fieldora readiness test failed"
    $openapi = (& $curlBinary @curlTrust https://127.0.0.1:8765/openapi.json) | ConvertFrom-Json
    Assert-Exit "Fieldora OpenAPI test failed"
    if (-not $openapi.openapi) { throw "OpenAPI document is invalid." }
    & $curlBinary @curlTrust https://127.0.0.1:8765/docs -o /dev/null
    Assert-Exit "Fieldora documentation test failed"

'@
    $core = $core.Substring(0, $curlStart) + $linuxCurl + $core.Substring($curlEnd)

    # Cosmetic/provenance corrections for Linux-generated handoff material.
    $core = $core.Replace('Internal root CA: $TrustRoot\ca-certificate.pem', 'Internal root CA: $(Join-Path $TrustRoot "ca-certificate.pem")')
    $core = $core.Replace('Credentials: $InstallRoot\ADMIN-CREDENTIALS.txt', 'Credentials: $(Join-Path $InstallRoot "ADMIN-CREDENTIALS.txt")')

    Set-Content -LiteralPath $tempCore -Encoding utf8NoBOM -Value $core
    [void][scriptblock]::Create($core)

    $invoke = @{
        InstallRoot = $InstallRoot
        FieldoraRef = $FieldoraRef
        AdminUsername = $AdminUsername
        AdminName = $AdminName
        Organization = $Organization
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword)) { $invoke.AdminPassword = $AdminPassword }
    & $tempCore @invoke
    if ($LASTEXITCODE -ne 0) { throw "Fieldora clean installer failed with exit code $LASTEXITCODE." }

    Write-Host ""
    Write-Host "==> Configuring temporary administrator credential handoff" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $handoffUrl -OutFile $tempHandoff -UseBasicParsing
    & $tempHandoff -InstallRoot $InstallRoot -RetentionDays $CredentialHandoffRetentionDays
    if ($LASTEXITCODE -ne 0) { throw "Bootstrap credential handoff configuration failed with exit code $LASTEXITCODE." }

    Write-Host ""
    Write-Host "==> Enabling internal mTLS storage-service listener" -ForegroundColor Cyan
    $overridePath = Join-Path $InstallRoot "compose.override.yaml"
    $override = @'
services:
  fieldora-server:
    environment:
      FIELDORA_STORAGE_SERVICE_ENABLED: "true"
      FIELDORA_STORAGE_SERVICE_HOST: "0.0.0.0"
      FIELDORA_STORAGE_SERVICE_PORT: "8766"
      FIELDORA_STORAGE_SERVICE_CERTIFICATE: "/run/fieldora-trust/service.crt"
      FIELDORA_STORAGE_SERVICE_PRIVATE_KEY: "/run/fieldora-trust/service.key"
      FIELDORA_STORAGE_SERVICE_CLIENT_CA: "/run/fieldora-trust/ca-certificate.pem"
    expose:
      - "8766"
'@
    Set-Content -LiteralPath $overridePath -Encoding utf8NoBOM -Value $override
    Push-Location $InstallRoot
    try {
        & docker compose config -q
        if ($LASTEXITCODE -ne 0) { throw "Storage-service Compose override is invalid." }
        & docker compose up -d --no-deps fieldora-server
        if ($LASTEXITCODE -ne 0) { throw "Unable to restart Fieldora server with the mTLS storage-service listener." }
        $healthy = $false
        foreach ($attempt in 1..45) {
            $state = (@(& docker inspect --format "{{.State.Health.Status}}" fieldora-server 2>$null) -join "").Trim()
            if ($state -eq "healthy") { $healthy = $true; break }
            Start-Sleep -Seconds 2
        }
        if (-not $healthy) {
            & docker compose logs --tail 150 fieldora-server
            throw "Fieldora server did not become healthy after enabling the mTLS storage-service listener."
        }
        $probe = @'
import ssl
import urllib.error
import urllib.request
context = ssl.create_default_context(cafile="/run/fieldora-trust/ca-certificate.pem")
context.load_cert_chain("/run/fieldora-trust/service.crt", "/run/fieldora-trust/service.key")
request = urllib.request.Request("https://fieldora-server:8766/internal/v1/storage/transport-probe", method="GET")
try:
    urllib.request.urlopen(request, context=context, timeout=5).read()
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
else:
    raise RuntimeError("unexpected storage-service probe response")
'@
        & docker compose exec -T fieldora-worker python3.11 -c $probe
        if ($LASTEXITCODE -ne 0) { throw "Internal mTLS storage-service handshake verification failed." }
    }
    finally { Pop-Location }
    Write-Host "Internal storage-service mTLS listener: VERIFIED" -ForegroundColor Green

    if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
        Write-Host ""
        Write-Host "==> Installing optional verified offline model bundle" -ForegroundColor Cyan
        Invoke-WebRequest -Uri $modelInstallerUrl -OutFile $tempModelInstaller -UseBasicParsing
        $modelInvoke = @{ InstallRoot = $InstallRoot; BundlePath = $OfflineModelBundle }
        if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) {
            $modelInvoke.TrustedSigningKey = $OfflineModelTrustedSigningKey
        }
        if ($RequireOfflineModelSignature) { $modelInvoke.RequireSignature = $true }
        if ($RequireOfflineModelCleanScan) { $modelInvoke.RequireCleanScan = $true }
        & $tempModelInstaller @modelInvoke
        if ($LASTEXITCODE -ne 0) { throw "Optional offline model installation failed with exit code $LASTEXITCODE." }

        $combinedOverride = @'
services:
  fieldora-server:
    environment:
      FIELDORA_STORAGE_SERVICE_ENABLED: "true"
      FIELDORA_STORAGE_SERVICE_HOST: "0.0.0.0"
      FIELDORA_STORAGE_SERVICE_PORT: "8766"
      FIELDORA_STORAGE_SERVICE_CERTIFICATE: "/run/fieldora-trust/service.crt"
      FIELDORA_STORAGE_SERVICE_PRIVATE_KEY: "/run/fieldora-trust/service.key"
      FIELDORA_STORAGE_SERVICE_CLIENT_CA: "/run/fieldora-trust/ca-certificate.pem"
      FIELDORA_MODEL_STORE: "/var/lib/fieldora-models"
    expose:
      - "8766"
    volumes:
      - ./fieldora-models:/var/lib/fieldora-models:ro
  fieldora-worker:
    environment:
      FIELDORA_MODEL_STORE: "/var/lib/fieldora-models"
    volumes:
      - ./fieldora-models:/var/lib/fieldora-models:ro
'@
        Set-Content -LiteralPath $overridePath -Encoding utf8NoBOM -Value $combinedOverride
        Remove-Item -LiteralPath (Join-Path $InstallRoot "compose.models.yaml") -Force -ErrorAction SilentlyContinue
        Push-Location $InstallRoot
        try {
            & docker compose config -q
            if ($LASTEXITCODE -ne 0) { throw "Combined storage-service and model-store Compose override is invalid." }
            & docker compose up -d --no-deps fieldora-server fieldora-worker
            if ($LASTEXITCODE -ne 0) { throw "Unable to apply combined storage-service and offline-model desired state." }
        }
        finally { Pop-Location }
        Write-Host "Offline model desired state: VERIFIED and preserved in compose.override.yaml" -ForegroundColor Green
    }

    $caPath = Join-Path $InstallRoot "service-trust/ca-certificate.pem"
    $credentialPath = Join-Path $InstallRoot "bootstrap-handoff/ADMIN-CREDENTIALS.txt"
    Write-Host ""
    Write-Host "FIELDORA LINUX CLEAN INSTALL PASSED" -ForegroundColor Green
    Write-Host "Browser URL: https://127.0.0.1:8765"
    Write-Host "Fieldora CA: $caPath"
    Write-Host "Temporary administrator credentials: $credentialPath"
    Write-Host "Credential handoff retention: $CredentialHandoffRetentionDays day(s)"
    if ([string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
        Write-Host "Offline models: optional; use Install-Fieldora-Offline-Model.ps1 when a verified local bundle is available."
    }
    else {
        Write-Host "Offline models: verified local bundle installed and mounted read-only."
    }
}
finally {
    Remove-Item -LiteralPath $tempCore -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempHandoff -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempModelInstaller -Force -ErrorAction SilentlyContinue
}
