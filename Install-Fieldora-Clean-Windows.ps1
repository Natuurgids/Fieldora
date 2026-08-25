<#
Windows entry point for the Fieldora clean Docker installer.
Runs the repository clean installer, configures temporary bootstrap credential handoff cleanup,
enables the internal mTLS storage-service listener, optionally installs a locally supplied
verified offline model bundle, installs the Fieldora root CA into the current user root store
through .NET X509Store (no certificate-store UI), verifies the exact thumbprint, then proves
HTTPS using the Windows trust store.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\FDTEST",
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
if (-not $IsWindows) { throw "This entry point is for Windows 11." }
if (($RequireOfflineModelSignature -or $RequireOfflineModelCleanScan) -and [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
    throw "Offline model verification switches require -OfflineModelBundle."
}

$encodedRef = [Uri]::EscapeDataString($FieldoraRef)
$url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef/Install-Fieldora-Clean.ps1"
$handoffUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef/Install-Fieldora-Bootstrap-Handoff.ps1"
$modelInstallerUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef/Install-Fieldora-Offline-Model.ps1"
if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') {
    $url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/Install-Fieldora-Clean.ps1"
    $handoffUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/Install-Fieldora-Bootstrap-Handoff.ps1"
    $modelInstallerUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/Install-Fieldora-Offline-Model.ps1"
}
$tempInstaller = Join-Path $env:TEMP "Install-Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).ps1"
$tempHandoffInstaller = Join-Path $env:TEMP "Install-Fieldora-Bootstrap-Handoff-$([Guid]::NewGuid().ToString('N')).ps1"
$tempModelInstaller = Join-Path $env:TEMP "Install-Fieldora-Offline-Model-$([Guid]::NewGuid().ToString('N')).ps1"
try {
    Invoke-WebRequest -Uri $url -OutFile $tempInstaller -UseBasicParsing
    $invoke = @{
        InstallRoot = $InstallRoot
        FieldoraRef = $FieldoraRef
        AdminUsername = $AdminUsername
        AdminName = $AdminName
        Organization = $Organization
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword)) {
        $invoke.AdminPassword = $AdminPassword
    }
    & $tempInstaller @invoke
    if ($LASTEXITCODE -ne 0) {
        throw "Fieldora clean installer failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> Configuring temporary administrator credential handoff" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Invoke-WebRequest -Uri $handoffUrl -OutFile $tempHandoffInstaller -UseBasicParsing
    & $tempHandoffInstaller -InstallRoot $InstallRoot -RetentionDays $CredentialHandoffRetentionDays
    if ($LASTEXITCODE -ne 0) {
        throw "Bootstrap credential handoff configuration failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> Enabling internal mTLS storage-service listener" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan

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
        if ($LASTEXITCODE -ne 0) {
            throw "Storage-service Compose override is invalid."
        }
        & docker compose up -d --no-deps fieldora-server
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to restart Fieldora server with the mTLS storage-service listener."
        }

        $healthy = $false
        foreach ($attempt in 1..45) {
            $state = (@(& docker inspect --format "{{.State.Health.Status}}" fieldora-server 2>$null) -join "").Trim()
            if ($state -eq "healthy") {
                $healthy = $true
                break
            }
            Start-Sleep -Seconds 2
        }
        if (-not $healthy) {
            & docker compose logs --tail 150 fieldora-server
            throw "Fieldora server did not become healthy after enabling the mTLS storage-service listener."
        }

        # Prove the internal listener performs a real mutual-TLS handshake. The worker
        # certificate is sufficient for the transport proof; storage operations still
        # require an enrolled ACTIVE storage-service identity at the application layer.
        $probe = @'
import ssl
import urllib.error
import urllib.request

context = ssl.create_default_context(cafile="/run/fieldora-trust/ca-certificate.pem")
context.load_cert_chain(
    "/run/fieldora-trust/service.crt",
    "/run/fieldora-trust/service.key",
)
request = urllib.request.Request(
    "https://fieldora-server:8766/internal/v1/storage/transport-probe",
    method="GET",
)
try:
    urllib.request.urlopen(request, context=context, timeout=5).read()
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
else:
    raise RuntimeError("unexpected storage-service probe response")
'@
        & docker compose exec -T fieldora-worker python3.11 -c $probe
        if ($LASTEXITCODE -ne 0) {
            throw "Internal mTLS storage-service handshake verification failed."
        }
    }
    finally {
        Pop-Location
    }
    Write-Host "Internal storage-service mTLS listener: VERIFIED (Docker network port 8766)" -ForegroundColor Green

    $caPath = Join-Path $InstallRoot "service-trust\ca-certificate.pem"
    if (-not (Test-Path -LiteralPath $caPath)) {
        throw "Fieldora root CA was not produced at $caPath"
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> Certifying Windows CurrentUser browser trust" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan

    # CreateFromPemFile(path) attempts to load an associated private key as well as
    # the certificate. The exported Fieldora trust file intentionally contains only
    # the public CA certificate because the root private key stays offline. Import
    # the certificate-only PEM explicitly instead.
    $pemText = [System.IO.File]::ReadAllText($caPath)
    try {
        $ca = [System.Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPem($pemText)
    }
    catch {
        throw "Could not parse the Fieldora public root CA PEM at $caPath. $($_.Exception.Message)"
    }
    if (-not $ca.Subject -or -not $ca.Thumbprint) {
        throw "Fieldora root CA PEM did not produce a valid X.509 certificate."
    }

    $store = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $store.Open(
            [System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite
        )
        foreach ($existing in @($store.Certificates | Where-Object {
            $_.Subject -eq "CN=Fieldora Internal Service CA - $Organization"
        })) {
            $store.Remove($existing)
        }
        $store.Add($ca)
    }
    finally {
        $store.Close()
    }

    $verify = [System.Security.Cryptography.X509Certificates.X509Store]::new(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    try {
        $verify.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
        $match = @($verify.Certificates | Where-Object { $_.Thumbprint -eq $ca.Thumbprint })
        if ($match.Count -ne 1) {
            throw "Windows CurrentUser root store does not contain the Fieldora CA thumbprint $($ca.Thumbprint)."
        }
    }
    finally {
        $verify.Close()
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw "curl.exe is required for Windows trust verification." }
    & curl.exe --fail --silent --show-error --ssl-revoke-best-effort https://127.0.0.1:8765/health/live -o NUL
    if ($LASTEXITCODE -ne 0) {
        throw "Windows trust-store HTTPS verification failed with exit code $LASTEXITCODE."
    }

    Write-Host "Windows CurrentUser Fieldora CA trust: VERIFIED" -ForegroundColor Green

    if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor DarkCyan
        Write-Host "==> Installing optional verified offline model bundle" -ForegroundColor Cyan
        Write-Host "============================================================" -ForegroundColor DarkCyan
        Invoke-WebRequest -Uri $modelInstallerUrl -OutFile $tempModelInstaller -UseBasicParsing
        $modelInvoke = @{
            InstallRoot = $InstallRoot
            BundlePath = $OfflineModelBundle
        }
        if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) {
            $modelInvoke.TrustedSigningKey = $OfflineModelTrustedSigningKey
        }
        if ($RequireOfflineModelSignature) {
            $modelInvoke.RequireSignature = $true
        }
        if ($RequireOfflineModelCleanScan) {
            $modelInvoke.RequireCleanScan = $true
        }
        & $tempModelInstaller @modelInvoke
        if ($LASTEXITCODE -ne 0) {
            throw "Optional offline model installation failed with exit code $LASTEXITCODE."
        }

        # Make both optional features part of the standard desired state. The portable
        # model helper keeps compose.models.yaml for standalone Linux/Windows use, but
        # a clean Windows deployment should remain correct with ordinary `docker compose`.
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
            if ($LASTEXITCODE -ne 0) {
                throw "Combined storage-service and model-store Compose override is invalid."
            }
            & docker compose up -d --no-deps fieldora-server fieldora-worker
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to apply the combined storage-service and offline-model desired state."
            }
        }
        finally {
            Pop-Location
        }
        Write-Host "Offline model desired state: VERIFIED and preserved in compose.override.yaml" -ForegroundColor Green
    }

    Write-Host "Browser URL: https://127.0.0.1:8765" -ForegroundColor Green
    Write-Host "Temporary administrator credentials: $InstallRoot\bootstrap-handoff\ADMIN-CREDENTIALS.txt" -ForegroundColor Green
    Write-Host "Credential handoff retention: $CredentialHandoffRetentionDays day(s)" -ForegroundColor Green
    if ([string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
        Write-Host "Offline models: optional; use Install-Fieldora-Offline-Model.ps1 when a verified local bundle is available." -ForegroundColor Green
    }
    else {
        Write-Host "Offline models: verified local bundle installed and mounted read-only." -ForegroundColor Green
    }
}
finally {
    Remove-Item -LiteralPath $tempInstaller -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempHandoffInstaller -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempModelInstaller -Force -ErrorAction SilentlyContinue
}
