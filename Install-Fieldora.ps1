<#
Canonical Fieldora installation selector.

Profiles:
- Fieldora: install the trusted Fieldora server/runtime only.
- FieldoraBastion: install Fieldora first, then the paired FieldoraBastion
  acquisition/quarantine tool boundary. Bastion is never installed as a
  replacement for Fieldora and is not auto-started as a network service.

The selector delegates to the existing certified platform-specific clean installer
or the certified paired installer so there is one user-facing installation choice
without duplicating deployment logic.
#>

[CmdletBinding()]
param(
    [ValidateSet("Fieldora","FieldoraBastion")]
    [string]$InstallProfile = "Fieldora",
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
    [switch]$RequireOfflineModelCleanScan,
    [string]$OfflineMapBundle = "",
    [string]$OfflineMapTrustedSigningKey = "",
    [switch]$RequireOfflineMapSignature,
    [switch]$RequireOfflineMapCleanScan
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 is required." }
if (-not ($IsWindows -or $IsLinux)) { throw "Fieldora installation supports Windows or Linux hosts." }

function Get-RepositoryScript {
    param([Parameter(Mandatory)][string]$Name)
    $local = Join-Path $PSScriptRoot $Name
    if (Test-Path -LiteralPath $local -PathType Leaf) { return $local }

    $encodedRef = [Uri]::EscapeDataString($FieldoraRef)
    $url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef/$Name"
    if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') {
        $url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/$Name"
    }
    $target = Join-Path ([IO.Path]::GetTempPath()) "Fieldora-$([Guid]::NewGuid().ToString('N'))-$Name"
    Invoke-WebRequest -Uri $url -OutFile $target -UseBasicParsing
    return $target
}

$temporaryScripts = [System.Collections.Generic.List[string]]::new()
try {
    Write-Host "Fieldora installation profile: $InstallProfile" -ForegroundColor Green
    if ($InstallProfile -eq "FieldoraBastion") {
        Write-Host "Full profile selected: Fieldora will be installed first, then FieldoraBastion." -ForegroundColor Cyan
        $installer = Get-RepositoryScript "Install-Fieldora-Paired.ps1"
        if (-not $installer.StartsWith($PSScriptRoot, [StringComparison]::OrdinalIgnoreCase)) { $temporaryScripts.Add($installer) }
        $invoke = @{
            InstallRoot = $InstallRoot
            FieldoraRef = $FieldoraRef
            BastionRef = $BastionRef
            AdminUsername = $AdminUsername
            AdminName = $AdminName
            Organization = $Organization
            CredentialHandoffRetentionDays = $CredentialHandoffRetentionDays
        }
        if (-not [string]::IsNullOrWhiteSpace($AdminPassword)) { $invoke.AdminPassword = $AdminPassword }
        if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) { $invoke.OfflineModelBundle = $OfflineModelBundle }
        if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) { $invoke.OfflineModelTrustedSigningKey = $OfflineModelTrustedSigningKey }
        if ($RequireOfflineModelSignature) { $invoke.RequireOfflineModelSignature = $true }
        if ($RequireOfflineModelCleanScan) { $invoke.RequireOfflineModelCleanScan = $true }
        if (-not [string]::IsNullOrWhiteSpace($OfflineMapBundle)) { $invoke.OfflineMapBundle = $OfflineMapBundle }
        if (-not [string]::IsNullOrWhiteSpace($OfflineMapTrustedSigningKey)) { $invoke.OfflineMapTrustedSigningKey = $OfflineMapTrustedSigningKey }
        if ($RequireOfflineMapSignature) { $invoke.RequireOfflineMapSignature = $true }
        if ($RequireOfflineMapCleanScan) { $invoke.RequireOfflineMapCleanScan = $true }
        & $installer @invoke
        if ($LASTEXITCODE -ne 0) { throw "FieldoraBastion full installation failed with exit code $LASTEXITCODE." }
        return
    }

    Write-Host "Fieldora-only profile selected; FieldoraBastion will not be installed." -ForegroundColor Cyan
    if (-not [string]::IsNullOrWhiteSpace($OfflineMapBundle)) {
        throw "OfflineMapBundle at clean-install time requires -InstallProfile FieldoraBastion. For Fieldora-only systems, import approved map packages afterward with Install-Fieldora-Offline-Media.ps1."
    }
    $wrapperName = if ($IsWindows) { "Install-Fieldora-Clean-Windows.ps1" } else { "Install-Fieldora-Clean-Linux.ps1" }
    $installer = Get-RepositoryScript $wrapperName
    if (-not $installer.StartsWith($PSScriptRoot, [StringComparison]::OrdinalIgnoreCase)) { $temporaryScripts.Add($installer) }
    $invoke = @{
        InstallRoot = $InstallRoot
        FieldoraRef = $FieldoraRef
        AdminUsername = $AdminUsername
        AdminName = $AdminName
        Organization = $Organization
        CredentialHandoffRetentionDays = $CredentialHandoffRetentionDays
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword)) { $invoke.AdminPassword = $AdminPassword }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelBundle)) { $invoke.OfflineModelBundle = $OfflineModelBundle }
    if (-not [string]::IsNullOrWhiteSpace($OfflineModelTrustedSigningKey)) { $invoke.OfflineModelTrustedSigningKey = $OfflineModelTrustedSigningKey }
    if ($RequireOfflineModelSignature) { $invoke.RequireOfflineModelSignature = $true }
    if ($RequireOfflineModelCleanScan) { $invoke.RequireOfflineModelCleanScan = $true }
    & $installer @invoke
    if ($LASTEXITCODE -ne 0) { throw "Fieldora installation failed with exit code $LASTEXITCODE." }
}
finally {
    foreach ($path in $temporaryScripts) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
}
