<#
Fieldora complete Docker bootstrap for Windows 11 + Docker Desktop.
Installs the repository-controlled Fieldora server stack and prepares/builds the
separate FieldoraBastion tool containers without collapsing security domains.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [switch]$NonInteractive,
    [string]$FieldoraRef = "f0146218d736d4579f50f4f6444ff3fd90e47574",
    [string]$BastionRef = "76163ab751630d2f1839dcad160cbd3276d82714",
    [string]$AdminUsername = "admin",
    [string]$AdminName = "Administrator",
    [string]$Organization = "local",
    [string]$AdminPassword = "",
    [string]$AdminPasswordFile = "",
    [ValidateRange(1,90)][int]$CredentialHandoffRetentionDays = 7
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
function Step([string]$Text) { Write-Host "`n============================================================" -ForegroundColor DarkCyan; Write-Host "==> $Text" -ForegroundColor Cyan; Write-Host "============================================================" -ForegroundColor DarkCyan }
function Assert-Exit([string]$Message) { if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" } }
function Get-RawUrl([string]$Repository,[string]$Ref,[string]$Path) { $encodedPath = ($Path -split '/' | ForEach-Object {[Uri]::EscapeDataString($_)}) -join '/'; return "https://raw.githubusercontent.com/$Repository/$Ref/$encodedPath" }
function Get-GitHubToken {
    foreach ($name in @('GH_TOKEN','GITHUB_TOKEN')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) { return $value.Trim() }
    }
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        $value = (& $gh.Source auth token 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($value)) { return $value }
    }
    return ''
}
function Download-Archive([string]$Repository,[string]$Ref,[string]$Destination) {
    $temp = [IO.Path]::GetTempPath(); $token = [Guid]::NewGuid().ToString('N'); $zip = Join-Path $temp "fieldora-$token.zip"; $extract = Join-Path $temp "fieldora-$token"
    try {
        New-Item -ItemType Directory -Force -Path $extract | Out-Null
        $encoded = [Uri]::EscapeDataString($Ref); $url = "https://api.github.com/repos/$Repository/zipball/$encoded"
        $headers = @{ Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28'; 'User-Agent' = 'Fieldora-Installer' }
        $githubToken = Get-GitHubToken
        if ($githubToken) { $headers.Authorization = "Bearer $githubToken" }
        try { Invoke-WebRequest -Uri $url -Headers $headers -OutFile $zip -UseBasicParsing }
        catch {
            if (-not $githubToken) { throw "Unable to download $Repository@$Ref. This repository may be private. Set GH_TOKEN/GITHUB_TOKEN or authenticate GitHub CLI with 'gh auth login', then rerun the installer." }
            throw
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $source = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1; if (-not $source) { throw "Archive for $Repository@$Ref was empty." }
        Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        Get-ChildItem -LiteralPath $source.FullName -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force }
    } finally { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue }
}
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    if ($NonInteractive) { throw "-InstallRoot is required with -NonInteractive." }
    $defaultRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Fieldora'
    $chosen = Read-Host "Installation directory [$defaultRoot]"
    $InstallRoot = if ([string]::IsNullOrWhiteSpace($chosen)) { $defaultRoot } else { $chosen.Trim().Trim('"') }
}
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$rootPath = [IO.Path]::GetPathRoot($InstallRoot).TrimEnd('\')
if ($InstallRoot.TrimEnd('\').Equals($rootPath,[StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing to install directly into a drive root.' }
if (Test-Path -LiteralPath $InstallRoot) {
    $entries = @(Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction Stop)
    $isFieldora = (Test-Path -LiteralPath (Join-Path $InstallRoot 'compose.yaml')) -or (Test-Path -LiteralPath (Join-Path $InstallRoot 'service-trust'))
    if ($entries.Count -gt 0 -and -not $isFieldora) { throw "Installation directory is not empty and is not an existing Fieldora installation: $InstallRoot" }
}
if (-not $IsWindows) { throw "Use the Linux complete installer on Linux hosts." }
if ($PSVersionTable.PSVersion.Major -lt 7) { throw "PowerShell 7 or newer is required." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI was not found. Install/start Docker Desktop first." }
& docker info *> $null; Assert-Exit "Docker Desktop is not running"
& docker compose version *> $null; Assert-Exit "Docker Compose v2 is unavailable"
$os = (& docker info --format '{{.OSType}}').Trim(); Assert-Exit "Unable to determine Docker container mode"; if ($os -ne 'linux') { throw "Docker Desktop must be using Linux containers; detected '$os'." }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot); $BastionRoot = Join-Path $InstallRoot "bastion"
$logName = "install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss")
$tempLogRoot = Join-Path ([IO.Path]::GetTempPath()) "Fieldora-Installer-Logs"; New-Item -ItemType Directory -Force -Path $tempLogRoot | Out-Null
$installLog = Join-Path $tempLogRoot $logName
Start-Transcript -LiteralPath $installLog -Force | Out-Null
Write-Host "Fieldora Complete Windows Docker Installer" -ForegroundColor Green
Write-Host "Fieldora : Natuurgids/Fieldora@$FieldoraRef"; Write-Host "Bastion  : Natuurgids/FieldoraBastion@$BastionRef"; Write-Host "Root     : $InstallRoot"
Write-Host "This is a destructive clean installation of the Fieldora server stack. Bastion remains a separate container security boundary." -ForegroundColor Yellow
$confirm = Read-Host "Type CLEAN to continue"; if ($confirm.Trim().ToUpperInvariant() -ne 'CLEAN') { Write-Host "Installation cancelled."; exit 0 }
$ownedPasswordFile = $null
$temp = [IO.Path]::GetTempPath(); $core = Join-Path $temp "Install-Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).ps1"; $handoff = Join-Path $temp "Install-Fieldora-Handoff-$([Guid]::NewGuid().ToString('N')).ps1"; $cleanInput = Join-Path $temp "Fieldora-Clean-$([Guid]::NewGuid().ToString('N')).txt"
try {
    Step "Downloading repository-controlled Fieldora installer"
    Invoke-WebRequest -Uri (Get-RawUrl 'Natuurgids/Fieldora' $FieldoraRef 'Install-Fieldora-Clean.ps1') -OutFile $core -UseBasicParsing
    # Both long-lived processes open the same staged-ingestion SQLite reference store.
    # On Docker Desktop, simultaneous first startup can race while SQLite switches the
    # database into WAL mode. Make the worker wait for the API health gate so schema/WAL
    # initialization has completed before the second process opens the store.
    $coreText = Get-Content -LiteralPath $core -Raw
    $workerMarker = "  fieldora-worker:`n    image: fieldora-v5-rocky:local`n    container_name: fieldora-worker`n    restart: unless-stopped`n    environment:`n      FIELDORA_SERVICE_ID: fieldora-worker-local`n      FIELDORA_HEARTBEAT_SECONDS: `"30`"`n    depends_on:`n      postgres:`n        condition: service_healthy"
    $workerReplacement = "$workerMarker`n      fieldora-server:`n        condition: service_healthy"
    if (-not $coreText.Contains($workerMarker)) { throw "Fieldora worker startup contract changed; refusing an unreviewed rewrite." }
    $coreText = $coreText.Replace($workerMarker, $workerReplacement)
    Set-Content -LiteralPath $core -Value $coreText -Encoding utf8NoBOM
    Step "Installing Fieldora server containers"
    Set-Content -LiteralPath $cleanInput -Value 'CLEAN' -Encoding ascii
    $coreArgs = @('-NoLogo','-NoProfile','-File',$core,'-InstallRoot',$InstallRoot,'-FieldoraRef',$FieldoraRef,'-AdminUsername',$AdminUsername,'-AdminName',$AdminName,'-Organization',$Organization)
    if ($AdminPassword -and $AdminPasswordFile) { throw "Use either AdminPassword or AdminPasswordFile, not both." }
    $forwardPasswordFile = $AdminPasswordFile
    $ownedPasswordFile = $null
    if ($AdminPassword) {
        $ownedPasswordFile = Join-Path $temp "Fieldora-Admin-$([Guid]::NewGuid().ToString('N')).secret"
        [IO.File]::WriteAllText($ownedPasswordFile, $AdminPassword)
        $forwardPasswordFile = $ownedPasswordFile
    }
    if ($forwardPasswordFile) { $coreArgs += @('-AdminPasswordFile',$forwardPasswordFile) }
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
    # The Fieldora root is a private local CA and intentionally has no public CRL/OCSP
    # distribution point. Windows curl uses Schannel, which otherwise treats the
    # unavailable revocation status as an error even when --cacert validates the chain.
    # Keep peer/hostname/CA verification enabled; suppress only that inapplicable lookup.
    $curlTls = @('--fail','--silent','--show-error','--ssl-no-revoke','--cacert',$ca)
    & curl.exe @curlTls https://127.0.0.1:8765/health/live | Out-Null; Assert-Exit "Fieldora live health check failed"
    & curl.exe @curlTls https://127.0.0.1:8765/health/ready | Out-Null; Assert-Exit "Fieldora readiness check failed"
    Step "Complete Docker environment installed"
    Write-Host "Fieldora root        : $InstallRoot" -ForegroundColor Green
    Write-Host "FieldoraBastion root : $BastionRoot" -ForegroundColor Green
    Write-Host "Bastion scanner and bundle-builder are hardened on-demand tool containers; they are built but not left running as idle services." -ForegroundColor Green
    Write-Host "Bootstrap credentials: $(Join-Path $InstallRoot 'bootstrap-handoff\ADMIN-CREDENTIALS.txt')" -ForegroundColor Yellow
} finally { Remove-Item -LiteralPath $core -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $handoff -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $cleanInput -Force -ErrorAction SilentlyContinue; if ($ownedPasswordFile) { Remove-Item -LiteralPath $ownedPasswordFile -Force -ErrorAction SilentlyContinue }; try { Stop-Transcript | Out-Null } catch {}; $finalLog = $installLog; if (Test-Path -LiteralPath $InstallRoot) { $finalLogRoot = Join-Path $InstallRoot 'logs'; New-Item -ItemType Directory -Force -Path $finalLogRoot | Out-Null; $finalLog = Join-Path $finalLogRoot $logName; Copy-Item -LiteralPath $installLog -Destination $finalLog -Force; Remove-Item -LiteralPath $installLog -Force -ErrorAction SilentlyContinue }; Write-Host "Sanitized installation log: $finalLog" -ForegroundColor Green }
