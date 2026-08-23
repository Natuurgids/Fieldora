<#
Windows entry point for the Fieldora clean Docker installer.
Runs the repository clean installer, installs the Fieldora root CA into the current
user root store through .NET X509Store (no certificate-store UI), verifies the exact
thumbprint, then proves HTTPS using the Windows trust store.
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\FDTEST",
    [string]$FieldoraRef = "feature/versioned-facility-floorplans",
    [string]$AdminUsername = "admin",
    [string]$AdminName = "Administrator",
    [string]$Organization = "local",
    [string]$AdminPassword = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 is required. Start pwsh and run this installer again."
}
if (-not $IsWindows) { throw "This entry point is for Windows 11." }

$encodedRef = [Uri]::EscapeDataString($FieldoraRef)
$url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$encodedRef/Install-Fieldora-Clean.ps1"
if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') {
    $url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$FieldoraRef/Install-Fieldora-Clean.ps1"
}
$tempInstaller = Join-Path $env:TEMP "Install-Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).ps1"
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
    Write-Host "Browser URL: https://127.0.0.1:8765" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tempInstaller -Force -ErrorAction SilentlyContinue
}
