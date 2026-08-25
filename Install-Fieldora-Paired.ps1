<#
Canonical paired clean installer for Fieldora + FieldoraBastion.

Fieldora remains the trusted application/PBAC boundary. FieldoraBastion is installed as a
separate dormant acquisition/quarantine toolset; its scanner and bundle builders are only
run explicitly and remain network-isolated according to the Bastion compose profiles.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = $(if ($IsWindows) { "D:\FDTEST" } else { Join-Path $HOME "fieldora-server" }),
    [string]$FieldoraRef = "feature/versioned-facility-floorplans",
    [string]$BastionRef = "f12f1f5c790174ab8c2114795b2da2ba379b9680",
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
    throw "PowerShell 7 is required."
}
if (-not ($IsWindows -or $IsLinux)) {
    throw "The paired clean installer supports Windows and Linux hosts."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required."
}

$encodedFieldoraRef = [Uri]::EscapeDataString($FieldoraRef)
$wrapperName = if ($IsWindows) { "Install-Fieldora-Clean-Windows.ps1" } else { "Install-Fieldora-Clean-Linux.ps1" }
$fieldoraUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedFieldoraRef/$wrapperName"
if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') {
    $fieldoraUrl = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/$wrapperName"
}
$tempWrapper = Join-Path ([IO.Path]::GetTempPath()) "Fieldora-Paired-$([Guid]::NewGuid().ToString('N')).ps1"

try {
    Write-Host "Installing Fieldora trusted server layer from $FieldoraRef..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $fieldoraUrl -OutFile $tempWrapper -UseBasicParsing
    $fieldoraArgs = @{
        InstallRoot = $InstallRoot
        FieldoraRef = $FieldoraRef
        AdminUsername = $AdminUsername
        AdminName = $AdminName
        Organization = $Organization
        CredentialHandoffRetentionDays = $CredentialHandoffRetentionDays
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword)) { $fieldoraArgs.AdminPassword = $AdminPassword }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) { $fieldoraArgs.OfflineModelBundle = $OfflineModelBundle }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) {
        $fieldoraArgs.OfflineModelTrustedSigningKey = $OfflineModelTrustedSigningKey
    }
    if ($RequireOfflineModelSignature) { $fieldoraArgs.RequireOfflineModelSignature = $true }
    if ($RequireOfflineModelCleanScan) { $fieldoraArgs.RequireOfflineModelCleanScan = $true }
    & $tempWrapper @fieldoraArgs
    if ($LASTEXITCODE -ne 0) { throw "Fieldora clean installation failed with exit code $LASTEXITCODE." }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> Installing paired FieldoraBastion tool boundary" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan

    $bastionRoot = Join-Path $InstallRoot "bastion"
    $sourceRoot = Join-Path $bastionRoot "source"
    New-Item -ItemType Directory -Force -Path $bastionRoot | Out-Null
    $archive = Join-Path ([IO.Path]::GetTempPath()) "fieldora-bastion-$([Guid]::NewGuid().ToString('N')).zip"
    $extract = Join-Path ([IO.Path]::GetTempPath()) "fieldora-bastion-$([Guid]::NewGuid().ToString('N'))"
    try {
        New-Item -ItemType Directory -Force -Path $extract | Out-Null
        $encodedBastionRef = [Uri]::EscapeDataString($BastionRef)
        $bastionUrl = "https://github.com/Natuurgids/FieldoraBastion/archive/refs/heads/$encodedBastionRef.zip"
        if ($BastionRef -match '^[0-9a-fA-F]{40}$') {
            $bastionUrl = "https://github.com/Natuurgids/FieldoraBastion/archive/$BastionRef.zip"
        }
        Write-Host "Downloading paired Bastion $BastionRef"
        Invoke-WebRequest -Uri $bastionUrl -OutFile $archive -UseBasicParsing
        Expand-Archive -Path $archive -DestinationPath $extract -Force
        $src = Get-ChildItem $extract -Directory | Select-Object -First 1
        if (-not $src) { throw "FieldoraBastion archive extraction failed." }
        New-Item -ItemType Directory -Force -Path $sourceRoot | Out-Null
        Get-ChildItem $src.FullName -Force | ForEach-Object {
            Copy-Item $_.FullName $sourceRoot -Recurse -Force
        }
    }
    finally {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "Containerfile"))) {
        throw "Paired FieldoraBastion source is incomplete."
    }
    foreach ($path in @(
        (Join-Path $bastionRoot "quarantine\model"),
        (Join-Path $bastionRoot "quarantine\maps"),
        (Join-Path $bastionRoot "approved"),
        (Join-Path $bastionRoot "scanner-db"),
        (Join-Path $bastionRoot "signing")
    )) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    & docker build -t fieldora-bastion:paired -f (Join-Path $sourceRoot "Containerfile") $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw "FieldoraBastion image build failed." }
    & docker run --rm fieldora-bastion:paired build-model-bundle --help *> $null
    if ($LASTEXITCODE -ne 0) { throw "Paired Bastion model-bundle CLI verification failed." }
    & docker run --rm fieldora-bastion:paired build-map-bundle --help *> $null
    if ($LASTEXITCODE -ne 0) { throw "Paired Bastion map-bundle CLI verification failed." }

    $pairing = [ordered]@{
        fieldora_ref = $FieldoraRef
        bastion_ref = $BastionRef
        bastion_image = "fieldora-bastion:paired"
        trust_boundary = "separate-quarantine-scan-sign-import"
        auto_started = $false
        model_quarantine = "bastion/quarantine/model"
        map_quarantine = "bastion/quarantine/maps"
        approved_bundles = "bastion/approved"
    }
    $pairing | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bastionRoot "PAIRING.json") -Encoding utf8NoBOM

    Write-Host "Fieldora + FieldoraBastion paired installation: VERIFIED" -ForegroundColor Green
    Write-Host "Bastion is installed but not auto-started; scanner/build tools remain explicit and isolated." -ForegroundColor Green
    Write-Host "Bastion pairing metadata: $bastionRoot\PAIRING.json" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tempWrapper -Force -ErrorAction SilentlyContinue
}
