<#
Fieldora complete Docker bootstrap for Windows 11 + Docker Desktop.
Installs the repository-controlled Fieldora server stack and prepares/builds the
separate FieldoraBastion tool containers without collapsing security domains.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "D:\FDTEST",
    [string]$FieldoraRef = "security/native-update-trust-hardening",
    [string]$BastionRef = "main",
    [string]$AdminUsername = "admin",
    [string]$AdminName = "Administrator",
    [string]$Organization = "local",
    [string]$AdminPassword = "",
    [ValidateRange(1,90)][int]$CredentialHandoffRetentionDays = 7
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
function Step([string]$Text) { Write-Host "`n============================================================" -ForegroundColor DarkCyan; Write-Host "==> $Text" -ForegroundColor Cyan; Write-Host "============================================================" -ForegroundColor DarkCyan }
function Assert-Exit([string]$Message) { if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" } }
function Get-RawUrl([string]$Repository,[string]$Ref,[string]$Path) { $encodedPath = ($Path -split '/' | ForEach-Object {[Uri]::EscapeDataString($_)}) -join '/'; return "https://raw.githubusercontent.com/$Repository/$Ref/$encodedPath" }
function Download-Archive([string]$Repository,[string]$Ref,[string]$Destination) {
    $temp = [IO.Path]::GetTempPath(); $token = [Guid]::NewGuid().ToString('N'); $zip = Join-Path $temp "fieldora-$token.zip"; $extract = Join-Path $temp "fieldora-$token"
    try {
        New-Item -ItemType Directory -Force -Path $extract | Out-Null
        $encoded = [Uri]::EscapeDataString($Ref); $url = "https://github.com/$Repository/archive/refs/heads/$encoded.zip"; if ($Ref -match '^[0-9a-fA-F]{40}$') { $url = "https://github.com/$Repository/archive/$Ref.zip" }
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $source = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1; if (-not $source) { throw "Archive for $Repository@$Ref was empty." }
        Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        Get-ChildItem -LiteralPath $source.FullName -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force }
    } finally { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue }
}
if (-not $IsWindows) { throw "Use the Linux complete installer on Linux hosts." }
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 or newer is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI was not found. Install/start Docker Desktop first." }
& docker info *> $null; Assert-Exit "Docker Desktop is not running"
& docker compose version *> $null; Assert-Exit "Docker Compose v2 is unavailable"
$os = (& docker info --format '{{.OSType}}').Trim(); Assert-Exit "Unable to determine Docker container mode"; if ($os -ne 'linux') { throw "Docker Desktop must be using Linux containers; detected '$os'." }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot); $BastionRoot = Join-Path $InstallRoot "bastion"
Write-Host "Fieldora Complete Windows Docker Installer" -ForegroundColor Green
Write-Host "Fieldora : Natuurgids/Fieldora@$FieldoraRef"; Write-Host "Bastion  : Natuurgids/FieldoraBastion@$BastionRef"; Write-Host "Root     : $InstallRoot"
Write-Host "This is a destructive clean installation of the Fieldora server stack. Bastion remains a separate container security boundary." -ForegroundColor Yellow
$confirm = Read-Host "Type CLEAN to continue"; if ($confirm.Trim().ToUpperInvariant() -ne 'CLEAN') { Write-Host "Installation cancelled."; exit 0 }
$temp = [IO.Path]::GetTempPath(); $core = Join-Path $temp "Install-Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).ps1"; $handoff = Join-Path $temp "Install-Fieldora-Handoff-$([Guid]::NewGuid().ToString('N')).ps1"; $cleanInput = Join-Path $temp "Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).txt"
try {
    Step "Downloading repository-controlled Fieldora installer"
    Invoke-WebRequest -Uri (Get-RawUrl 'Natuurgids/Fieldora' $FieldoraRef 'Install-Fieldora-Clean.ps1') -OutFile $core -UseBasicParsing
    Step "Installing Fieldora server containers"
    Set-Content -LiteralPath $cleanInput -Value 'CLEAN' -Encoding ascii
    $coreArgs = @('-NoLogo','-NoProfile','-File',$core,'-InstallRoot',$InstallRoot,'-FieldoraRef',$FieldoraRef,'-AdminUsername',$AdminUsername,'-AdminName',$AdminName,'-Organization',$Organization)
    if ($AdminPassword) { $coreArgs += @('-AdminPassword',$AdminPassword) }
    $process = Start-Process -FilePath (Get-Command pwsh).Source -ArgumentList $coreArgs -RedirectStandardInput $cleanInput -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Fieldora clean installer failed (exit code $($process.ExitCode))." }
    Step "Configuring temporary administrator credential handoff"
    Invoke-WebRequest -Uri (Get-RawUrl 'Natuurgids/Fieldora' $FieldoraRef 'Install-Fieldora-Bootstrap-Handoff.ps1') -OutFile $handoff -UseBasicParsing
    & $handoff -InstallRoot $InstallRoot -RetentionDays $CredentialHandoffRetentionDays
    if (-not $?) { throw "Credential handoff configuration failed." }
    Step "Preparing FieldoraBastion security boundary"
    Download-Archive -Repository 'Natuurgids/FieldoraBastion' -Ref $BastionRef -Destination $BastionRoot
    foreach ($dir in @('quarantine','approved','scanner-db','signing')) { New-Item -ItemType Directory -Force -Path (Join-Path $BastionRoot $dir) | Out-Null }
    Push-Location $BastionRoot
    try {
        & docker compose config *> $null; Assert-Exit "FieldoraBastion compose configuration is invalid"
        & docker compose --profile tools build; Assert-Exit "FieldoraBastion tool image build failed"
    } finally { Pop-Location }
    Step "Verifying Fieldora server"
    $ca = Join-Path $InstallRoot 'service-trust\ca-certificate.pem'; if (-not (Test-Path -LiteralPath $ca)) { throw "Fieldora service CA was not created." }
    & curl.exe --fail --silent --show-error --cacert $ca https://127.0.0.1:8765/health/live | Out-Null; Assert-Exit "Fieldora live health check failed"
    & curl.exe --fail --silent --show-error --cacert $ca https://127.0.0.1:8765/health/ready | Out-Null; Assert-Exit "Fieldora readiness check failed"
    Step "Complete Docker environment installed"
    Write-Host "Fieldora root        : $InstallRoot" -ForegroundColor Green
    Write-Host "FieldoraBastion root : $BastionRoot" -ForegroundColor Green
    Write-Host "Bastion scanner and bundle-builder are hardened on-demand tool containers; they are built but not left running as idle services." -ForegroundColor Green
    Write-Host "Bootstrap credentials: $(Join-Path $InstallRoot 'bootstrap-handoff\ADMIN-CREDENTIALS.txt')" -ForegroundColor Yellow
} finally { Remove-Item -LiteralPath $core -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $handoff -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $cleanInput -Force -ErrorAction SilentlyContinue }
