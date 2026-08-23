<#
Fieldora clean Docker installer for Windows 11 + Docker Desktop.

This is a destructive clean-room installer for the disposable test root
(default D:\FDTEST). Keep this script outside that root, for example D:\DF.

Security and lifecycle model:
- Fieldora browser/API listener is HTTPS.
- PostgreSQL network access requires TLS plus a trusted client certificate.
- API, worker, PostgreSQL and certificate-renewal controller have durable identities.
- Short-lived service certificates renew automatically without changing identity.
- The long-lived installation root CA key is never mounted into running services.
- A constrained issuer performs online renewal; the API hot-reloads renewed TLS keys.
- PostgreSQL reloads renewed TLS material with pg_reload_conf(), not a container restart.
- Long-lived services use restart: unless-stopped and explicit Operator lifecycle state.
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

$ApiServiceId = "fieldora-api-local"
$WorkerServiceId = "fieldora-worker-local"
$PostgresServiceId = "fieldora-postgres-local"
$RenewerServiceId = "fieldora-cert-renewer-local"
$CertificateHours = 168
$RenewBeforeHours = 48

function Step([string]$Text) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "==> $Text" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
}

function Assert-Exit([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)" }
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

function Docker-Output {
    param([Parameter(Mandatory)][scriptblock]$Command)
    return (@(& $Command) -join "`n").Trim()
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
Write-Host "Trust  : mandatory HTTPS + PostgreSQL mutual TLS + automatic renewal"
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
foreach ($name in @("fieldora-server","fieldora-worker","fieldora-cert-renewer","fieldora-postgres")) {
    $found = (@(& docker ps -a --filter "name=^/${name}$" --format "{{.Names}}") -join "").Trim()
    if ($found -eq $name) { & docker rm -f $name *> $null }
}
foreach ($volume in @(
    "fieldora-api-trust",
    "fieldora-worker-trust",
    "fieldora-postgres-trust",
    "fieldora-renewer-trust",
    "fieldora-issuer-authority"
)) {
    $found = (@(& docker volume ls --filter "name=^${volume}$" --format "{{.Name}}") -join "").Trim()
    if ($found -eq $volume) { & docker volume rm $volume *> $null }
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
$TrustRoot = Join-Path $InstallRoot "service-trust"
$PgTlsConfigRoot = Join-Path $InstallRoot "postgres-mtls"
$RenewalRoot = Join-Path $InstallRoot "certificate-renewal"
foreach ($p in @($InstallRoot,$SourceRoot,$PgDataRoot,$FieldoraData,$SecretsRoot,$InitRoot,$TrustRoot,$PgTlsConfigRoot,$RenewalRoot)) {
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
Write-Host "Downloading $url"
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
Set-Content -Path (Join-Path $PgTlsConfigRoot "pg_hba.conf") -Encoding ascii -Value @'
local   all   all                                 trust
hostssl all   all   0.0.0.0/0   scram-sha-256 clientcert=verify-full
hostssl all   all   ::/0        scram-sha-256 clientcert=verify-full
hostnossl all all   0.0.0.0/0   reject
hostnossl all all   ::/0        reject
'@

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

Step "Creating database secrets"
$sslQuery = "sslmode=verify-full&sslrootcert=/run/fieldora-trust/ca-certificate.pem&sslcert=/run/fieldora-trust/service.crt&sslkey=/run/fieldora-trust/service.key"
$dsns = @{
    "fieldora-access-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_access?$sslQuery"
    "fieldora-science-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_science?$sslQuery"
    "fieldora-jobs-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_jobs?$sslQuery"
    "fieldora-media-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_media?$sslQuery"
    "fieldora-exports-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_exports?$sslQuery"
    "fieldora-governance-dsn"="postgresql://fieldora:${PostgresPassword}@postgres:5432/fieldora_governance?$sslQuery"
}
foreach ($k in $dsns.Keys) { Set-Content (Join-Path $SecretsRoot $k) -Encoding ascii -NoNewline -Value $dsns[$k] }
Set-Content (Join-Path $SecretsRoot "postgres-password") -Encoding ascii -NoNewline -Value $PostgresPassword

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
    command:
      - postgres
      - -c
      - ssl=on
      - -c
      - ssl_cert_file=/run/fieldora-trust/postgres.crt
      - -c
      - ssl_key_file=/run/fieldora-trust/postgres.key
      - -c
      - ssl_ca_file=/run/fieldora-trust/ca-certificate.pem
      - -c
      - hba_file=/run/fieldora-trust/pg_hba.conf
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
      - ./postgres-init:/docker-entrypoint-initdb.d:ro
      - ./secrets/postgres-password:/run/secrets/postgres-password:ro
      - fieldora-postgres-trust:/run/fieldora-trust:ro
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
    environment:
      FIELDORA_SERVICE_ID: fieldora-api-local
      FIELDORA_HEARTBEAT_SECONDS: "30"
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
      - --tls-certificate
      - /run/fieldora-trust/service.crt
      - --tls-private-key
      - /run/fieldora-trust/service.key
    volumes:
      - ./fieldora-data:/var/lib/fieldora
      - ./secrets/fieldora-access-dsn:/run/secrets/fieldora-access-dsn:ro
      - ./secrets/fieldora-science-dsn:/run/secrets/fieldora-science-dsn:ro
      - ./secrets/fieldora-jobs-dsn:/run/secrets/fieldora-jobs-dsn:ro
      - ./secrets/fieldora-media-dsn:/run/secrets/fieldora-media-dsn:ro
      - ./secrets/fieldora-exports-dsn:/run/secrets/fieldora-exports-dsn:ro
      - ./secrets/fieldora-governance-dsn:/run/secrets/fieldora-governance-dsn:ro
      - fieldora-api-trust:/run/fieldora-trust:ro
    ports:
      - "127.0.0.1:8765:8765"
    healthcheck:
      test: ["CMD", "python3.11", "-c", "import ssl,urllib.request; c=ssl.create_default_context(cafile='/run/fieldora-trust/ca-certificate.pem'); urllib.request.urlopen('https://127.0.0.1:8765/health/ready',context=c,timeout=4).read()"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 20s
    networks: [fieldora-network]

  fieldora-worker:
    image: fieldora-v5-rocky:local
    container_name: fieldora-worker
    restart: unless-stopped
    environment:
      FIELDORA_SERVICE_ID: fieldora-worker-local
      FIELDORA_HEARTBEAT_SECONDS: "30"
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
      - run-job-worker
      - --worker-id
      - fieldora-worker-local
      - --continuous
      - --poll-seconds
      - "2"
      - --lease-seconds
      - "300"
    volumes:
      - ./fieldora-data:/var/lib/fieldora
      - ./secrets/fieldora-access-dsn:/run/secrets/fieldora-access-dsn:ro
      - ./secrets/fieldora-science-dsn:/run/secrets/fieldora-science-dsn:ro
      - ./secrets/fieldora-jobs-dsn:/run/secrets/fieldora-jobs-dsn:ro
      - ./secrets/fieldora-media-dsn:/run/secrets/fieldora-media-dsn:ro
      - ./secrets/fieldora-exports-dsn:/run/secrets/fieldora-exports-dsn:ro
      - ./secrets/fieldora-governance-dsn:/run/secrets/fieldora-governance-dsn:ro
      - fieldora-worker-trust:/run/fieldora-trust:ro
    networks: [fieldora-network]

  fieldora-cert-renewer:
    image: fieldora-v5-rocky:local
    container_name: fieldora-cert-renewer
    user: "0:0"
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    command:
      - fieldora-certificate-renewer
      - --authority-root
      - /run/fieldora-authority
      - --postgres-dsn-file
      - /run/secrets/fieldora-governance-dsn
      - --config
      - /run/fieldora-renewal/config.json
      - --interval-seconds
      - "3600"
      - --renew-before-hours
      - "48"
      - --lifetime-hours
      - "168"
    volumes:
      - ./secrets/fieldora-governance-dsn:/run/secrets/fieldora-governance-dsn:ro
      - ./certificate-renewal/config.json:/run/fieldora-renewal/config.json:ro
      - fieldora-issuer-authority:/run/fieldora-authority:ro
      - fieldora-renewer-trust:/run/fieldora-trust
      - fieldora-api-trust:/targets/api
      - fieldora-worker-trust:/targets/worker
      - fieldora-postgres-trust:/targets/postgres
    networks: [fieldora-network]

networks:
  fieldora-network:
    driver: bridge

volumes:
  fieldora-api-trust:
    name: fieldora-api-trust
  fieldora-worker-trust:
    name: fieldora-worker-trust
  fieldora-postgres-trust:
    name: fieldora-postgres-trust
  fieldora-renewer-trust:
    name: fieldora-renewer-trust
  fieldora-issuer-authority:
    name: fieldora-issuer-authority
'@
Set-Content (Join-Path $InstallRoot "compose.yaml") -Encoding utf8NoBOM -Value $compose

Push-Location $InstallRoot
try {
    & docker compose config -q
    Assert-Exit "Generated Compose configuration is invalid"

    Step "Building Fieldora image"
    & docker compose build --pull --no-cache fieldora-server
    Assert-Exit "Fieldora image build failed"

    $FieldoraUid = [int](Docker-Output { docker run --rm fieldora-v5-rocky:local id -u fieldora })
    Assert-Exit "Unable to determine Fieldora container uid"
    $FieldoraGid = [int](Docker-Output { docker run --rm fieldora-v5-rocky:local id -g fieldora })
    Assert-Exit "Unable to determine Fieldora container gid"
    $PostgresUid = [int](Docker-Output { docker run --rm postgres:16 id -u postgres })
    Assert-Exit "Unable to determine PostgreSQL container uid"
    $PostgresGid = [int](Docker-Output { docker run --rm postgres:16 id -g postgres })
    Assert-Exit "Unable to determine PostgreSQL container gid"

    Step "Creating Fieldora internal root and constrained service issuer"
    & docker run --rm --user 0 -v "${TrustRoot}:/trust" fieldora-v5-rocky:local fieldora-service-trust --root /trust init-ca --common-name "Fieldora Internal Service CA - $Organization"
    Assert-Exit "Internal CA creation failed"
    foreach ($requiredTrustFile in @("ca-private.pem","ca-certificate.pem","issuer-private.pem","issuer-certificate.pem")) {
        if (-not (Test-Path (Join-Path $TrustRoot $requiredTrustFile))) { throw "Trust initialization is missing $requiredTrustFile" }
    }

    $apiJson = Docker-Output { docker run --rm --user 0 -v "${TrustRoot}:/trust" fieldora-v5-rocky:local fieldora-service-trust --root /trust issue --service-id $ApiServiceId --organization $Organization --common-name fieldora --certificate /trust/api.crt --private-key /trust/api.key --dns fieldora-server --dns localhost --ip 127.0.0.1 --hours $CertificateHours }
    Assert-Exit "API service certificate creation failed"
    $apiCertificate = $apiJson | ConvertFrom-Json

    $workerJson = Docker-Output { docker run --rm --user 0 -v "${TrustRoot}:/trust" fieldora-v5-rocky:local fieldora-service-trust --root /trust issue --service-id $WorkerServiceId --organization $Organization --common-name fieldora --certificate /trust/worker.crt --private-key /trust/worker.key --dns fieldora-worker --hours $CertificateHours }
    Assert-Exit "Worker service certificate creation failed"
    $workerCertificate = $workerJson | ConvertFrom-Json

    $postgresJson = Docker-Output { docker run --rm --user 0 -v "${TrustRoot}:/trust" fieldora-v5-rocky:local fieldora-service-trust --root /trust issue --service-id $PostgresServiceId --organization $Organization --common-name postgres --certificate /trust/postgres.crt --private-key /trust/postgres.key --dns postgres --hours $CertificateHours }
    Assert-Exit "PostgreSQL service certificate creation failed"
    $postgresCertificate = $postgresJson | ConvertFrom-Json

    $renewerJson = Docker-Output { docker run --rm --user 0 -v "${TrustRoot}:/trust" fieldora-v5-rocky:local fieldora-service-trust --root /trust issue --service-id $RenewerServiceId --organization $Organization --common-name fieldora --certificate /trust/renewer.crt --private-key /trust/renewer.key --dns fieldora-cert-renewer --hours $CertificateHours }
    Assert-Exit "Certificate renewer identity creation failed"
    $renewerCertificate = $renewerJson | ConvertFrom-Json

    foreach ($volume in @("fieldora-api-trust","fieldora-worker-trust","fieldora-postgres-trust","fieldora-renewer-trust","fieldora-issuer-authority")) {
        & docker volume create $volume *> $null
        Assert-Exit "Unable to create trust volume $volume"
    }

    & docker run --rm --user 0 -v "${TrustRoot}:/source:ro" -v fieldora-api-trust:/target fieldora-v5-rocky:local sh -lc "cp /source/ca-certificate.pem /target/ca-certificate.pem && cp /source/api.crt /target/service.crt && cp /source/api.key /target/service.key && chown ${FieldoraUid}:${FieldoraGid} /target/* && chmod 644 /target/ca-certificate.pem /target/service.crt && chmod 600 /target/service.key"
    Assert-Exit "Unable to provision API trust volume"

    & docker run --rm --user 0 -v "${TrustRoot}:/source:ro" -v fieldora-worker-trust:/target fieldora-v5-rocky:local sh -lc "cp /source/ca-certificate.pem /target/ca-certificate.pem && cp /source/worker.crt /target/service.crt && cp /source/worker.key /target/service.key && chown ${FieldoraUid}:${FieldoraGid} /target/* && chmod 644 /target/ca-certificate.pem /target/service.crt && chmod 600 /target/service.key"
    Assert-Exit "Unable to provision worker trust volume"

    & docker run --rm --user 0 -v "${TrustRoot}:/source:ro" -v "${PgTlsConfigRoot}:/config:ro" -v fieldora-postgres-trust:/target postgres:16 bash -lc "cp /source/ca-certificate.pem /target/ca-certificate.pem && cp /source/postgres.crt /target/postgres.crt && cp /source/postgres.key /target/postgres.key && cp /config/pg_hba.conf /target/pg_hba.conf && chown ${PostgresUid}:${PostgresGid} /target/* && chmod 644 /target/ca-certificate.pem /target/postgres.crt /target/pg_hba.conf && chmod 600 /target/postgres.key"
    Assert-Exit "Unable to provision PostgreSQL trust volume"

    & docker run --rm --user 0 -v "${TrustRoot}:/source:ro" -v fieldora-renewer-trust:/target fieldora-v5-rocky:local sh -lc "cp /source/ca-certificate.pem /target/ca-certificate.pem && cp /source/renewer.crt /target/service.crt && cp /source/renewer.key /target/service.key && chown 0:0 /target/* && chmod 644 /target/ca-certificate.pem /target/service.crt && chmod 600 /target/service.key"
    Assert-Exit "Unable to provision renewer trust volume"

    & docker run --rm --user 0 -v "${TrustRoot}:/source:ro" -v fieldora-issuer-authority:/target fieldora-v5-rocky:local sh -lc "cp /source/ca-certificate.pem /target/ca-certificate.pem && cp /source/issuer-certificate.pem /target/issuer-certificate.pem && cp /source/issuer-private.pem /target/issuer-private.pem && chown 0:0 /target/* && chmod 644 /target/ca-certificate.pem /target/issuer-certificate.pem && chmod 600 /target/issuer-private.pem"
    Assert-Exit "Unable to provision constrained issuer authority"

    $renewalConfig = @{
        services = @(
            @{ service_id=$ApiServiceId; organization_id=$Organization; common_name="fieldora"; certificate="/targets/api/service.crt"; private_key="/targets/api/service.key"; dns_names=@("fieldora-server","localhost"); ip_addresses=@("127.0.0.1"); uid=$FieldoraUid; gid=$FieldoraGid },
            @{ service_id=$WorkerServiceId; organization_id=$Organization; common_name="fieldora"; certificate="/targets/worker/service.crt"; private_key="/targets/worker/service.key"; dns_names=@("fieldora-worker"); ip_addresses=@(); uid=$FieldoraUid; gid=$FieldoraGid },
            @{ service_id=$PostgresServiceId; organization_id=$Organization; common_name="postgres"; certificate="/targets/postgres/postgres.crt"; private_key="/targets/postgres/postgres.key"; dns_names=@("postgres"); ip_addresses=@(); uid=$PostgresUid; gid=$PostgresGid; reload_postgres=$true },
            @{ service_id=$RenewerServiceId; organization_id=$Organization; common_name="fieldora"; certificate="/run/fieldora-trust/service.crt"; private_key="/run/fieldora-trust/service.key"; dns_names=@("fieldora-cert-renewer"); ip_addresses=@(); uid=0; gid=0 }
        )
    }
    $renewalConfig | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $RenewalRoot "config.json") -Encoding utf8NoBOM

    Step "Starting PostgreSQL with mandatory mutual TLS"
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

    Step "Verifying PostgreSQL mutual-TLS client authentication"
    & docker compose run --rm --no-deps fieldora-server python3.11 -c "import pathlib,psycopg; d=pathlib.Path('/run/secrets/fieldora-governance-dsn').read_text().strip(); c=psycopg.connect(d,connect_timeout=10); print(c.execute('select 1').fetchone()[0]); c.close()"
    Assert-Exit "Fieldora could not establish its mutually authenticated PostgreSQL connection"

    Step "Enrolling durable Fieldora services"
    & docker compose run --rm --no-deps fieldora-server fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn enroll --organization $Organization --service-id $ApiServiceId --name "Fieldora API (local)" --type api --node docker-desktop --certificate-serial $apiCertificate.serial_number --certificate-not-after-epoch $apiCertificate.not_after_epoch
    Assert-Exit "API service enrollment failed"
    & docker compose run --rm --no-deps fieldora-server fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn activate --service-id $ApiServiceId *> $null
    Assert-Exit "API service activation failed"

    & docker compose run --rm --no-deps fieldora-worker fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn enroll --organization $Organization --service-id $WorkerServiceId --name "Fieldora Job Worker (local)" --type worker --node docker-desktop --certificate-serial $workerCertificate.serial_number --certificate-not-after-epoch $workerCertificate.not_after_epoch
    Assert-Exit "Worker service enrollment failed"
    & docker compose run --rm --no-deps fieldora-worker fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn activate --service-id $WorkerServiceId *> $null
    Assert-Exit "Worker service activation failed"

    & docker compose run --rm --no-deps fieldora-server fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn enroll --organization $Organization --service-id $PostgresServiceId --name "Fieldora PostgreSQL (local)" --type database --node docker-desktop --certificate-serial $postgresCertificate.serial_number --certificate-not-after-epoch $postgresCertificate.not_after_epoch
    Assert-Exit "PostgreSQL service enrollment failed"
    & docker compose run --rm --no-deps fieldora-server fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn activate --service-id $PostgresServiceId *> $null
    Assert-Exit "PostgreSQL service activation failed"

    & docker compose run --rm --no-deps fieldora-cert-renewer fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn enroll --organization $Organization --service-id $RenewerServiceId --name "Fieldora Certificate Renewer (local)" --type trust-renewer --node docker-desktop --certificate-serial $renewerCertificate.serial_number --certificate-not-after-epoch $renewerCertificate.not_after_epoch
    Assert-Exit "Certificate renewer enrollment failed"
    & docker compose run --rm --no-deps fieldora-cert-renewer fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn activate --service-id $RenewerServiceId *> $null
    Assert-Exit "Certificate renewer activation failed"

    Step "Bootstrapping Fieldora administrator"
    & docker compose run --rm --no-deps fieldora-server fieldora-server --data-root /var/lib/fieldora --access-backend postgresql --postgres-access-dsn-file /run/secrets/fieldora-access-dsn init-user --organization $Organization --name $AdminName --username $AdminUsername --password $AdminPassword
    Assert-Exit "Administrator bootstrap failed"

    Set-Content (Join-Path $InstallRoot "ADMIN-CREDENTIALS.txt") -Encoding utf8NoBOM -Value @"
Fieldora local Docker administrator
===================================
Username: $AdminUsername
Password: $AdminPassword
Organization: $Organization
Fieldora: https://127.0.0.1:8765
Source ref: $FieldoraRef
API service: $ApiServiceId
Worker service: $WorkerServiceId
PostgreSQL service: $PostgresServiceId
Certificate renewer: $RenewerServiceId
Internal root CA: $TrustRoot\ca-certificate.pem
"@

    Step "Trusting the local Fieldora HTTPS certificate for the current Windows user"
    try {
        $existing = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Subject -eq "CN=Fieldora Internal Service CA - $Organization" }
        foreach ($certificate in $existing) { Remove-Item -LiteralPath $certificate.PSPath -Force }
        Import-Certificate -FilePath (Join-Path $TrustRoot "ca-certificate.pem") -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
        Write-Host "Fieldora internal root CA trusted for CurrentUser." -ForegroundColor Green
    } catch {
        Write-Warning "Could not add the Fieldora CA to CurrentUser trust. The server still uses TLS; your browser may require manual trust. $($_.Exception.Message)"
    }

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

    foreach ($container in @("fieldora-worker","fieldora-cert-renewer")) {
        $state = (@(& docker inspect --format "{{.State.Status}}" $container 2>$null) -join "").Trim()
        if ($state -ne "running") { docker compose logs --tail 300 $container; throw "$container is not running." }
    }

    Step "Running live no-restart certificate renewal test"
    & docker compose run --rm --no-deps fieldora-cert-renewer fieldora-certificate-renewer --authority-root /run/fieldora-authority --postgres-dsn-file /run/secrets/fieldora-governance-dsn --config /run/fieldora-renewal/config.json --interval-seconds 3600 --renew-before-hours 168 --lifetime-hours 168 --once
    Assert-Exit "Forced certificate renewal test failed"

    Step "Running clean-install smoke tests"
    & docker compose exec -T postgres pg_isready -U fieldora -d postgres
    Assert-Exit "PostgreSQL smoke test failed"

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw "curl.exe is required for TLS smoke testing on Windows 11." }
    $caFile = Join-Path $TrustRoot "ca-certificate.pem"
    & curl.exe --fail --silent --show-error --cacert $caFile https://127.0.0.1:8765/ -o NUL
    Assert-Exit "Fieldora HTTPS root test failed after live certificate renewal"
    $live = (& curl.exe --fail --silent --show-error --cacert $caFile https://127.0.0.1:8765/health/live) | ConvertFrom-Json
    Assert-Exit "Fieldora liveness test failed"
    $ready = (& curl.exe --fail --silent --show-error --cacert $caFile https://127.0.0.1:8765/health/ready) | ConvertFrom-Json
    Assert-Exit "Fieldora readiness test failed"
    $openapi = (& curl.exe --fail --silent --show-error --cacert $caFile https://127.0.0.1:8765/openapi.json) | ConvertFrom-Json
    Assert-Exit "Fieldora OpenAPI test failed"
    if (-not $openapi.openapi) { throw "OpenAPI document is invalid." }
    & curl.exe --fail --silent --show-error --cacert $caFile https://127.0.0.1:8765/docs -o NUL
    Assert-Exit "Fieldora documentation test failed"

    $servicesJson = Docker-Output { docker compose run --rm --no-deps fieldora-server fieldora-operator --postgres-dsn-file /run/secrets/fieldora-governance-dsn list --organization $Organization }
    Assert-Exit "Operator registry verification failed"
    $services = @($servicesJson | ConvertFrom-Json)
    foreach ($requiredService in @($ApiServiceId,$WorkerServiceId,$PostgresServiceId,$RenewerServiceId)) {
        if ($services.service_id -notcontains $requiredService) { throw "Operator registry is missing $requiredService" }
    }

    $rootKeyMountCheck = Docker-Output { docker inspect fieldora-cert-renewer --format '{{range .Mounts}}{{println .Destination}}{{end}}' }
    if ($rootKeyMountCheck -match 'service-trust') { throw "Root CA directory must never be mounted into the renewal service." }

    Write-Host ""
    Write-Host "FIELDORA CLEAN INSTALL PASSED" -ForegroundColor Green
    Write-Host "Fieldora: https://127.0.0.1:8765"
    Write-Host "Docs:     https://127.0.0.1:8765/docs"
    Write-Host "User:     $AdminUsername"
    Write-Host "Password: $AdminPassword"
    Write-Host "Credentials: $InstallRoot\ADMIN-CREDENTIALS.txt"
    Write-Host "API service:       $ApiServiceId"
    Write-Host "Worker service:    $WorkerServiceId"
    Write-Host "PostgreSQL service:$PostgresServiceId"
    Write-Host "Trust renewer:     $RenewerServiceId"
    Write-Host "Certificate renewal: automatic, no routine service restart"
    Write-Host "Root CA private key: offline from running containers"
    Write-Host "Restart policy: unless-stopped"
}
finally {
    Pop-Location
}