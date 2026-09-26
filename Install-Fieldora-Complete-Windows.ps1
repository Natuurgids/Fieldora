<#
Fieldora complete Docker bootstrap for Windows 11 + Docker Desktop.
This bootstrap preserves the reviewed complete-installer flow while applying the
LAN endpoint contract before execution: selected host binding, certificate SANs,
renewal SANs, and hostname-verified health checks.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [switch]$NonInteractive,
    [string]$FieldoraRef = "42114cd537724fa4b1e123dd8ae51cbfe2373187",
    [string]$BastionRef = "76163ab751630d2f1839dcad160cbd3276d82714",
    [string]$AdminUsername = "admin",
    [string]$AdminName = "Administrator",
    [string]$Organization = "local",
    [string]$PublicHostname = "",
    [string]$ListenAddress = "",
    [string]$AdminPassword = "",
    [string]$AdminPasswordFile = "",
    [ValidateRange(1,90)][int]$CredentialHandoffRetentionDays = 7
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Last reviewed complete installer before the LAN endpoint repair. Downloading it
# by immutable SHA keeps this bootstrap deterministic and avoids self-recursion.
$BaseInstallerRef = "42114cd537724fa4b1e123dd8ae51cbfe2373187"
$temp = [IO.Path]::GetTempPath()
$base = Join-Path $temp "Fieldora-Complete-Base-$([Guid]::NewGuid().ToString('N')).ps1"
$patched = Join-Path $temp "Fieldora-Complete-LAN-$([Guid]::NewGuid().ToString('N')).ps1"
try {
    $url = "https://raw.githubusercontent.com/Natuurgids/Fieldora/$BaseInstallerRef/Install-Fieldora-Complete-Windows.ps1"
    Invoke-WebRequest -Uri $url -OutFile $base -UseBasicParsing
    $text = Get-Content -LiteralPath $base -Raw

    $anchor = '$coreText = $coreText.Replace($workerMarker, $workerReplacement)'
    if (-not $text.Contains($anchor)) { throw "Base installer worker contract changed; refusing an unreviewed LAN rewrite." }
    $lanPatch = @'
$coreText = $coreText.Replace($workerMarker, $workerReplacement)
    # Preserve localhost for local maintenance while publishing the organization-selected
    # interface as a second binding. The API certificate and renewal policy carry the same
    # DNS/IP endpoint so TLS hostname verification remains valid after automatic renewal.
    if (-not [Net.IPAddress]::IsLoopback($listenIp)) {
        $portMarker = '      - "127.0.0.1:8765:8765"'
        if (-not $coreText.Contains($portMarker)) { throw "Fieldora port publication contract changed; refusing an unreviewed LAN rewrite." }
        $coreText = $coreText.Replace($portMarker, "$portMarker`n      - `"${ListenAddress}:8765:8765`"")
    }
    $issueMarker = '--dns fieldora-server --dns localhost --ip 127.0.0.1 --hours $CertificateHours'
    if (-not $coreText.Contains($issueMarker)) { throw "Fieldora API certificate contract changed; refusing an unreviewed LAN rewrite." }
    $coreText = $coreText.Replace($issueMarker, '--dns fieldora-server --dns localhost --dns $PublicHostname --ip 127.0.0.1 --ip $ListenAddress --hours $CertificateHours')
    $renewMarker = 'dns_names=@("fieldora-server","localhost"); ip_addresses=@("127.0.0.1")'
    if (-not $coreText.Contains($renewMarker)) { throw "Fieldora certificate renewal contract changed; refusing an unreviewed LAN rewrite." }
    $coreText = $coreText.Replace($renewMarker, 'dns_names=@("fieldora-server","localhost",$PublicHostname); ip_addresses=@("127.0.0.1",$ListenAddress)')
'@
    $text = $text.Replace($anchor, $lanPatch.TrimEnd())

    # Resolve the selected hostname directly to the selected interface for installer
    # verification. This validates the hostname SAN without requiring DNS to exist yet.
    $curlMarker = '$curlTls = @(''--fail'',''--silent'',''--show-error'',''--ssl-no-revoke'',''--cacert'',$ca)'
    if (-not $text.Contains($curlMarker)) { throw "Base installer TLS verification contract changed; refusing an unreviewed LAN rewrite." }
    $curlReplacement = '$curlTls = @(''--fail'',''--silent'',''--show-error'',''--ssl-no-revoke'',''--cacert'',$ca,''--resolve'',"${PublicHostname}:8765:${ListenAddress}")'
    $text = $text.Replace($curlMarker, $curlReplacement)
    Set-Content -LiteralPath $patched -Value $text -Encoding utf8NoBOM

    $args = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$patched,
        '-FieldoraRef',$FieldoraRef,'-BastionRef',$BastionRef,
        '-AdminUsername',$AdminUsername,'-AdminName',$AdminName,'-Organization',$Organization,
        '-CredentialHandoffRetentionDays',$CredentialHandoffRetentionDays)
    if ($InstallRoot) { $args += @('-InstallRoot',$InstallRoot) }
    if ($NonInteractive) { $args += '-NonInteractive' }
    if ($PublicHostname) { $args += @('-PublicHostname',$PublicHostname) }
    if ($ListenAddress) { $args += @('-ListenAddress',$ListenAddress) }
    if ($AdminPassword -and $AdminPasswordFile) { throw "Use either AdminPassword or AdminPasswordFile, not both." }
    if ($AdminPassword) { $args += @('-AdminPassword',$AdminPassword) }
    if ($AdminPasswordFile) { $args += @('-AdminPasswordFile',$AdminPasswordFile) }

    & (Get-Command pwsh).Source @args
    if ($LASTEXITCODE -ne 0) { throw "Fieldora complete installer failed (exit code $LASTEXITCODE)." }
} finally {
    Remove-Item -LiteralPath $base -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $patched -Force -ErrorAction SilentlyContinue
}
