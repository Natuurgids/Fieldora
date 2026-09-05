<#
Real-host certification harness for the repository-controlled Fieldora clean installer.

This script is intentionally destructive and must only be used on disposable certification
hosts. Windows is pinned to D:\FDTEST. Linux certification is accepted only on Rocky Linux 9.
It installs the exact supplied Fieldora commit, then emits a bounded JSON proof without
including administrator credentials, trust private keys, model bytes, or filesystem content.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Windows11','RockyLinux9')]
    [string]$Platform,
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$FieldoraRef,
    [string]$InstallRoot = '',
    [string]$OutputPath = '',
    [string]$OfflineModelBundle = '',
    [string]$OfflineModelTrustedSigningKey = '',
    [switch]$RequireOfflineModelSignature,
    [switch]$RequireOfflineModelCleanScan,
    [switch]$AllowDestructiveInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $AllowDestructiveInstall) {
    throw 'Refusing destructive runtime certification without -AllowDestructiveInstall.'
}
if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 is required.'
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is required.'
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker engine is unavailable.' }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is unavailable.' }

if ($Platform -eq 'Windows11') {
    if (-not $IsWindows) { throw 'Windows11 certification must run on Windows.' }
    $osVersion = [System.Environment]::OSVersion.Version
    if ($osVersion.Major -lt 10 -or $osVersion.Build -lt 22000) {
        throw "Windows 11 build 22000 or later is required; found $osVersion."
    }
    if ([string]::IsNullOrWhiteSpace($InstallRoot)) { $InstallRoot = 'D:\FDTEST' }
    $expected = [IO.Path]::GetFullPath('D:\FDTEST').TrimEnd([IO.Path]::DirectorySeparatorChar)
    $actual = [IO.Path]::GetFullPath($InstallRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if ($actual -ne $expected) {
        throw "Windows runtime certification is pinned to D:\FDTEST; received $actual."
    }
    $entryPoint = 'Install-Fieldora-Clean-Windows.ps1'
    $hostIdentity = "Windows $osVersion"
}
else {
    if (-not $IsLinux) { throw 'RockyLinux9 certification must run on Linux.' }
    $osRelease = @{}
    foreach ($line in Get-Content -LiteralPath '/etc/os-release') {
        if ($line -match '^([A-Z_]+)=(.*)$') {
            $osRelease[$matches[1]] = $matches[2].Trim('"')
        }
    }
    if (($osRelease['ID'] -ne 'rocky') -or (-not $osRelease['VERSION_ID'].StartsWith('9'))) {
        throw "Real-host Linux certification requires Rocky Linux 9; found ID=$($osRelease['ID']) VERSION_ID=$($osRelease['VERSION_ID'])."
    }
    if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
        $InstallRoot = '/var/tmp/fieldora-runtime-certification'
    }
    $installFull = [IO.Path]::GetFullPath($InstallRoot)
    if ($installFull -ne '/var/tmp/fieldora-runtime-certification') {
        throw "Rocky runtime certification is pinned to /var/tmp/fieldora-runtime-certification; received $installFull."
    }
    $entryPoint = 'Install-Fieldora-Clean-Linux.ps1'
    $hostIdentity = "Rocky Linux $($osRelease['VERSION_ID'])"
}

if (($RequireOfflineModelSignature -or $RequireOfflineModelCleanScan) -and [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
    throw 'Offline model verification switches require -OfflineModelBundle.'
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path (Get-Location) "fieldora-runtime-certification-$Platform-$FieldoraRef.json"
}

$entryUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/$entryPoint"
$tempEntry = Join-Path ([IO.Path]::GetTempPath()) "$entryPoint-$([Guid]::NewGuid().ToString('N')).ps1"
$started = [DateTimeOffset]::UtcNow

function Assert-Container([string]$Name) {
    $running = (@(& docker inspect --format '{{.State.Running}}' $Name 2>$null) -join '').Trim()
    if ($LASTEXITCODE -ne 0 -or $running -ne 'true') { throw "$Name is not running." }
    $restartCount = [int]((@(& docker inspect --format '{{.RestartCount}}' $Name) -join '').Trim())
    if ($restartCount -ne 0) { throw "$Name restarted $restartCount time(s) during runtime certification." }
    return @{ name=$Name; running=$true; restart_count=$restartCount }
}

function Invoke-PrivateCaCurl([string]$Path, [switch]$DiscardBody) {
    $caPath = Join-Path $InstallRoot 'service-trust/ca-certificate.pem'
    if (-not (Test-Path -LiteralPath $caPath)) { throw "Fieldora public CA is missing at $caPath." }
    $curl = if ($IsWindows) { Get-Command curl.exe -ErrorAction Stop } else { Get-Command curl -ErrorAction Stop }
    $args = @('--fail','--silent','--show-error','--cacert',$caPath)
    # Fieldora's private/offline CA intentionally has no Internet-reachable revocation service.
    # Schannel otherwise fails a valid private-CA chain with CRYPT_E_NO_REVOCATION_CHECK.
    # Best-effort preserves certificate/hostname verification and any available revocation checks;
    # unlike --ssl-no-revoke or --insecure it does not disable TLS trust validation.
    if ($IsWindows) { $args += '--ssl-revoke-best-effort' }
    $args += "https://127.0.0.1:8765$Path"
    if ($DiscardBody) { $args += @('-o', $(if ($IsWindows) { 'NUL' } else { '/dev/null' })) }
    $body = @(& $curl.Source @args)
    if ($LASTEXITCODE -ne 0) { throw "HTTPS check failed for $Path." }
    return ($body -join "`n")
}

try {
    Invoke-WebRequest -Uri $entryUrl -OutFile $tempEntry -UseBasicParsing
    $entryText = Get-Content -LiteralPath $tempEntry -Raw
    [void][scriptblock]::Create($entryText)

    $invoke = @{
        InstallRoot = $InstallRoot
        FieldoraRef = $FieldoraRef
    }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) {
        $invoke.OfflineModelBundle = $OfflineModelBundle
    }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) {
        $invoke.OfflineModelTrustedSigningKey = $OfflineModelTrustedSigningKey
    }
    if ($RequireOfflineModelSignature) { $invoke.RequireOfflineModelSignature = $true }
    if ($RequireOfflineModelCleanScan) { $invoke.RequireOfflineModelCleanScan = $true }

    & $tempEntry @invoke
    if ($LASTEXITCODE -ne 0) { throw "Clean installer failed with exit code $LASTEXITCODE." }

    Push-Location $InstallRoot
    try {
        & docker compose config -q
        if ($LASTEXITCODE -ne 0) { throw 'Installed Compose desired state is invalid.' }
        $services = @(
            (Assert-Container 'fieldora-postgres'),
            (Assert-Container 'fieldora-server'),
            (Assert-Container 'fieldora-worker'),
            (Assert-Container 'fieldora-cert-renewer')
        )
    }
    finally { Pop-Location }

    $live = Invoke-PrivateCaCurl '/health/live'
    $ready = Invoke-PrivateCaCurl '/health/ready'
    $openapi = Invoke-PrivateCaCurl '/openapi.json'
    Invoke-PrivateCaCurl '/' -DiscardBody
    Invoke-PrivateCaCurl '/docs' -DiscardBody
    if (-not ($live | ConvertFrom-Json).live) { throw 'Liveness payload is not live.' }
    if (-not ($ready | ConvertFrom-Json).ready) { throw 'Readiness payload is not ready.' }
    if (-not ($openapi | ConvertFrom-Json).openapi) { throw 'OpenAPI payload is invalid.' }

    $credentialPath = Join-Path $InstallRoot 'bootstrap-handoff/ADMIN-CREDENTIALS.txt'
    if (-not (Test-Path -LiteralPath $credentialPath)) {
        throw 'Temporary administrator credential handoff file is missing.'
    }
    $credentialInfo = Get-Item -LiteralPath $credentialPath
    if ($credentialInfo.Length -le 0) { throw 'Temporary administrator credential handoff file is empty.' }

    $overridePath = Join-Path $InstallRoot 'compose.override.yaml'
    $override = Get-Content -LiteralPath $overridePath -Raw
    foreach ($needle in @(
        'FIELDORA_STORAGE_SERVICE_ENABLED: "true"',
        'FIELDORA_STORAGE_SERVICE_PORT: "8766"',
        'FIELDORA_STORAGE_SERVICE_CLIENT_CA:'
    )) {
        if (-not $override.Contains($needle)) { throw "Installed desired state is missing storage mTLS marker: $needle" }
    }

    $modelInstalled = -not [string]::IsNullOrWhiteSpace($OfflineModelBundle)
    if ($modelInstalled) {
        foreach ($needle in @('FIELDORA_MODEL_STORE: "/var/lib/fieldora-models"','./fieldora-models:/var/lib/fieldora-models:ro')) {
            if (-not $override.Contains($needle)) { throw "Installed desired state is missing offline-model marker: $needle" }
        }
    }

    $dockerVersion = (@(& docker version --format '{{.Server.Version}}') -join '').Trim()
    $composeVersion = (@(& docker compose version --short) -join '').Trim()
    $finished = [DateTimeOffset]::UtcNow
    $proof = [ordered]@{
        schema = 'fieldora.clean-runtime-certification.v1'
        fieldora_ref = $FieldoraRef.ToLowerInvariant()
        platform = $Platform
        host_identity = $hostIdentity
        started_at = $started.ToString('O')
        completed_at = $finished.ToString('O')
        docker_server_version = $dockerVersion
        docker_compose_version = $composeVersion
        install_root = $InstallRoot
        services = $services
        https = @{ live=$true; ready=$true; openapi=$true; root=$true; docs=$true }
        credential_handoff = @{ present=$true; size_bytes=$credentialInfo.Length; content_recorded=$false }
        storage_service_mtls_desired_state = $true
        offline_model = @{ installed=$modelInstalled; mounted_read_only=$modelInstalled }
        secrets_or_payloads_recorded = $false
    }
    $proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM
    Write-Host "FIELDORA REAL-HOST RUNTIME CERTIFICATION PASSED" -ForegroundColor Green
    Write-Host "Proof: $OutputPath" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tempEntry -Force -ErrorAction SilentlyContinue
}
