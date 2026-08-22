<#
Fieldora clean Docker installer for Windows 11 + Docker Desktop.
This installer is intentionally destructive to the disposable test root (default D:\FDTEST).
Keep this file outside the installation root when running it.
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

function Step([string]$Text) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> $Text" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
}

function Assert-Exit([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" }
}

function Safe-Output([scriptblock]$Command) {
    return (@(& $Command) -join "").Trim()
}

function New-Password {
    $bytes = New-Object byte[] 18
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return "Fd!$([Convert]::ToHexString($bytes).ToLowerInvariant())"
}

function Remove-WithRetry([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($attempt in 1..6) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force
            return
        } catch {
            if ($attempt -eq 6) {
                throw "Cannot remove $Path. Close every shell, Explorer window or editor using it and retry. $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 2
        }
    }
}

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "PowerShell 7 is required. Start pwsh, cd to the directory containing this installer, and run it again."
}

$installFull = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$currentFull = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\')
$scriptDir = [IO.Path]::GetFullPath((Split-Path -Parent $PSCommandPath)).TrimEnd('\')
function Inside([string]$Candidate, [string]$Parent) {
    if ($Candidate.Equals($Parent,[StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $Candidate.StartsWith($Parent + '\',[StringComparison]::OrdinalIgnoreCase)
}
if ((Inside $currentFull $installFull) -or (Inside $scriptDir $installFull)) {
    throw "Do not run this installer from inside $InstallRoot. Keep it somewhere such as D:\DF."
}

Write-Host ""
Write-Host "Fieldora V5 Clean Docker Installer" -ForegroundColor Green
Write-Host "Target : $InstallRoot"
Write-Host "Ref    : $FieldoraRef"
Write-Host ""
Write-Host "WARNING: this deletes the complete disposable installation and PostgreSQL data under $InstallRoot." -ForegroundColor Yellow
if ((Read-Host "Type CLEAN to continue").Trim().ToUpperInvariant() -ne "CLEAN") {
    Write-Host "Installation cancelled."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($AdminPassword)) { $AdminPassword = New-Password }
if ($AdminPassword.Length -lt 12) { throw "Administrator password must be at least 12 characters." }
$PostgresPassword = New-Password

Step "Checking Docker Desktop"
if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw "docker.exe was not found." }
try { & docker info *> $null } catch { }
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop Linux engine is not running." }
$dockerOs = (@(& docker info --format '{{.OSType}}') -join "").Trim()
Assert-Exit "Unable to inspect Docker"
if ($dockerOs -ne "linux") { throw "Docker Desktop must use Linux containers." }
& docker compose version *> $null
Assert-Exit "Docker Compose is unavailable"
Write-Host "Docker engine: READY" -ForegroundColor Green

Step "Removing previous Fieldora test installation"
$oldCompose = Join-Path $InstallRoot "compose.yaml"
if (Test-Path -LiteralPath $oldCompose) {
    & docker compose -f $oldCompose down --volumes --remove-orphans --timeout 30 2>$null
}
foreach ($name in @("fieldora-server","fieldora-postgres")) {
    $found = (@(& docker ps -a --filter "name=^/${name}$" --format "{{.Names}}") -join "").Trim()
    if ($found -eq $name) { & docker rm -f $name *> $null }
}
$network = (@(& docker network ls --filter "name=^fieldora_fieldora-network$" --format "{{.Name}}") -join "").Trim()
if ($network -eq "fieldora_fieldora-network") { & docker network rm fieldora_fieldora-network *> $null }
if ((& docker images --format "{{.Repository}}:{{.Tag}}") -contains "fieldora-v5-rocky:local") {
    & docker image rm -f fieldora-v5-rocky:local *> $null
}
Remove-WithRetry $InstallRoot

Step "Creating clean installation"
$SourceRoot = Join-Path $InstallRoot "source"
$PgDataRoot = Join-Path $InstallRoot "postgres-data"
$FieldoraData = Join-Path $InstallRoot "fieldora-data"
$SecretsRoot = Join-Path $InstallRoot "secrets"
$InitRoot = Join-Path $InstallRoot "postgres-init"
foreach ($p in @($InstallRoot,$SourceRoot,$PgDataRoot,$FieldoraData,$SecretsRoot,$InitRoot)) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}

Step "Downloading Fieldora source"
$encodedRef = [Uri]::EscapeDataString($FieldoraRef)
$zip = Join-Path $env:TEMP "fieldora-source.zip"
$extract = Join-Path $env:TEMP "fieldora-source-extract"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $extract | Out-Null
$url = "https://github.com/Natuurgids/Fieldora/archive/refs/heads/$encodedRef.zip"
if ($FieldoraRef -match '^[0-9a-fA-F]{40}$') { $url = "https://github.com/Natuurgids/Fieldora/archive/$FieldoraRef.zip" }
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $extract -Force
$src = Get-ChildItem $extract -Directory | Select-Object -First 1
if (-not $src) { throw "Source archive extraction failed." }
Get-ChildItem $src.FullName -Force | ForEach-Object { Copy-Item $_.FullName $SourceRoot -Recurse -Force }
Remove-Item $zip -Force
Remove-Item $extract -Recurse -Force
if (-not (Test-Path (Join-Path $SourceRoot "pyproject.toml"))) { throw "Source archive is incomplete." }

Step "Creating PostgreSQL initialization"
$databases = @(
    "fieldora_access",
    "fieldora_science",
    "fieldora_jobs",
    "fieldora_media",
    "fieldora_exports",
    "fieldora_governance"
)
for ($i=0; $i -lt $databases.Count; $i++) {
    $n = "{0:D2}" -f ($i+1)
    Set-Content -Path (Join-Path $InitRoot "$n-create-$($databases[$i]).sql") -Encoding utf8NoBOM -Value "CREATE DATABASE $($databases[$i]);"
}

Step "Creating database secrets"
$dsns = @{
    "fieldora-access-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_access"
    "fieldora-science-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_science"
    "fieldora-jobs-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_jobs"
    "fieldora-media-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_media"
    "fieldora-exports-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_exports"
    "fieldora-governance-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_governance"
}
foreach ($k in $dsns.Keys) { Set-Content (Join-Path $SecretsRoot $k) -Encoding ascii -NoNewline -Value $dsns[$k] }
Set-Content (Join-Path $SecretsRoot "postgres-password") -Encoding ascii -NoNewline -Value $PostgresPassword

Step "Creating Rocky Linux Fieldora image"
$dockerfile = @'
FROM rockylinux:9
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN dnf -y update \
 && dnf -y install python3.11 python3.11-pip ca-certificates shadow-utils \
 && dnf clean all && rm -rf /var/cache/dnf
WORKDIR /opt/fieldora
COPY . /opt/fieldora
RUN python3.11 -m pip install --upgrade pip \
 && python3.11 -m pip install ".[server-postgresql]"
RUN groupadd --system fieldora \
 && useradd --system --gid fieldora --home-dir /var/lib/fieldora --create-home fieldora \
 && mkdir -p /var/lib/fieldora \
 && chown -R fieldora:fieldora /var/lib/fieldora /opt/fieldora
USER fieldora
EXPOSE 8765
CMD ["fieldora-server","--help"]
'@
Set-Content (Join-Path $SourceRoot "Dockerfile.fieldora") -Encoding utf8NoBOM -Value $dockerfile

Step "Creating Docker Compose stack"
$compose = @'
name: fieldora
services:
  postgres:
    image: postgres:16
    container_name: fieldora-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: fieldora
      POSTGRES_DB: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres-password
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
      - ./postgres-init:/docker-entrypoint-initdb.d:ro
      - ./secrets/postgres-password:/run/secrets/postgres-password:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fieldora -d postgres"]
      interval: 5s
      timeout: 5s
      retries: 30
      start_period: 5s
    networks: [fieldora-network]

  fieldora-server:
    build:
      context: ./source
      dockerfile: Dockerfile.fieldora
    image: fieldora-v5-rocky:local
    container_name: fieldora-server
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    command:
      - fieldora-server
      - --data-root
      - /var/lib/fieldora
      - --access-backend
      - postgresql
      - --postgres-access-dsn-file
      - /run/secrets/fieldora-access-dsn
      - --science-backend
      - postgresql
      - --postgres-science-dsn-file
      - /run/secrets/fieldora-science-dsn
      - --job-backend
      - postgresql
      - --postgres-jobs-dsn-file
      - /run/secrets/fieldora-jobs-dsn
      - --media-metadata-backend
      - postgresql
      - --postgres-media-dsn-file
      - /run/secrets/fieldora-media-dsn
      - --export-metadata-backend
      - postgresql
      - --postgres-exports-dsn-file
      - /run/secrets/fieldora-exports-dsn
      - --governance-backend
      - postgresql
      - --postgres-governance-dsn-file
      - /run/secrets/fieldora-governance-dsn
      - serve
      - --host
      - 0.0.0.0
      - --port
      - "8765"
      - --allow-insecure-http
    volumes:
      - ./fieldora-data:/var/lib/fieldora
      - ./secrets/fieldora-access-dsn:/run/secrets/fieldora-access-dsn:ro
      - ./secrets/fieldora-science-dsn:/run/secrets/fieldora-science-dsn:ro
      - ./secrets/fieldora-jobs-dsn:/run/secrets/fieldora-jobs-dsn:ro
      - ./secrets/fieldora-media-dsn:/run/secrets/fieldora-media-dsn:ro
      - ./secrets/fieldora-exports-dsn:/run/secrets/fieldora-exports-dsn:ro
      - ./secrets/fieldora-governance-dsn:/run/secrets/fieldora-governance-dsn:ro
    ports:
      - "127.0.0.1:8765:8765"
    healthcheck:
      test: ["CMD", "python3.11", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health/ready',timeout=4).read()"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 20s
    networks: [fieldora-network]
networks:
  fieldora-network:
    driver: bridge
'@
Set-Content (Join-Path $InstallRoot "compose.yaml") -Encoding utf8NoBOM -Value $compose

Push-Location $InstallRoot
try {
    & docker compose config -q
    Assert-Exit "Generated Compose configuration is invalid"

    Step "Building Fieldora image"
    & docker compose build --pull --no-cache fieldora-server
    Assert-Exit "Fieldora image build failed"

    Step "Starting PostgreSQL"
    & docker compose up -d postgres
    Assert-Exit "PostgreSQL failed to start"

    $healthy = $false
    foreach ($attempt in 1..60) {
        $s = (@(& docker inspect --format "{{.State.Health.Status}}" fieldora-postgres 2>$null) -join "").Trim()
        if ($s -eq "healthy") { $healthy = $true; break }
        Write-Host "PostgreSQL health: $s ($attempt/60)" -ForegroundColor DarkYellow
        Start-Sleep 2
    }
    if (-not $healthy) { docker compose logs --tail 250 postgres; throw "PostgreSQL did not become healthy." }

    Write-Host "Waiting for all six databases to finish initialization..."
    $allReady = $false
    $present = @()
    foreach ($attempt in 1..90) {
        $present = @(& docker compose exec -T postgres psql -U fieldora -d postgres -Atc "SELECT datname FROM pg_database ORDER BY datname;" 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $missing = @($databases | Where-Object { $present -notcontains $_ })
            if ($missing.Count -eq 0) { $allReady = $true; break }
            Write-Host "Waiting for: $($missing -join ', ') ($attempt/90)" -ForegroundColor DarkYellow
        }
        Start-Sleep 2
    }
    if (-not $allReady) { docker compose logs --tail 300 postgres; throw "Not all Fieldora databases were created." }
    foreach ($db in $databases) { Write-Host "$db : OK" -ForegroundColor Green }

    Step "Bootstrapping Fieldora administrator"
    & docker compose run --rm --no-deps fieldora-server fieldora-server --data-root /var/lib/fieldora --access-backend postgresql --postgres-access-dsn-file /run/secrets/fieldora-access-dsn init-user --organization $Organization --name $AdminName --username $AdminUsername --password $AdminPassword
    Assert-Exit "Administrator bootstrap failed"

    Set-Content (Join-Path $InstallRoot "ADMIN-CREDENTIALS.txt") -Encoding utf8NoBOM -Value @"
Fieldora local Docker administrator
===================================
Username: $AdminUsername
Password: $AdminPassword
Organization: $Organization
Fieldora: http://127.0.0.1:8765
Source ref: $FieldoraRef
"@

    Step "Starting complete Fieldora stack"
    & docker compose up -d
    Assert-Exit "Fieldora stack failed to start"

    $serverHealthy = $false
    foreach ($attempt in 1..60) {
        $s = (@(& docker inspect --format "{{.State.Health.Status}}" fieldora-server 2>$null) -join "").Trim()
        if ($s -eq "healthy") { $serverHealthy = $true; break }
        Write-Host "Fieldora health: $s ($attempt/60)" -ForegroundColor DarkYellow
        Start-Sleep 2
    }
    if (-not $serverHealthy) { docker compose logs --tail 300 fieldora-server; throw "Fieldora did not become healthy." }

    Step "Running smoke tests"
    & docker compose exec -T postgres pg_isready -U fieldora -d postgres
    Assert-Exit "PostgreSQL smoke test failed"
    if ((Invoke-WebRequest http://127.0.0.1:8765/ -UseBasicParsing -TimeoutSec 10).StatusCode -ne 200) { throw "Root HTTP test failed." }
    $live = Invoke-RestMethod http://127.0.0.1:8765/health/live -TimeoutSec 10
    $ready = Invoke-RestMethod http://127.0.0.1:8765/health/ready -TimeoutSec 10
    $openapi = Invoke-RestMethod http://127.0.0.1:8765/openapi.json -TimeoutSec 10
    if (-not $openapi.openapi) { throw "OpenAPI test failed." }
    if ((Invoke-WebRequest http://127.0.0.1:8765/docs -UseBasicParsing -TimeoutSec 10).StatusCode -ne 200) { throw "Docs HTTP test failed." }

    Write-Host ""
    Write-Host "FIELDORA CLEAN INSTALL PASSED" -ForegroundColor Green
    Write-Host "Fieldora: http://127.0.0.1:8765"
    Write-Host "Docs:     http://127.0.0.1:8765/docs"
    Write-Host "User:     $AdminUsername"
    Write-Host "Password: $AdminPassword"
    Write-Host "Credentials: $InstallRoot\ADMIN-CREDENTIALS.txt"
    Write-Host "Restart policy: unless-stopped"
}
finally {
    Pop-Location
}
