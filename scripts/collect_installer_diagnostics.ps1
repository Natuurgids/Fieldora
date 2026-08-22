[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $env:TEMP ("Aperture-Installer-Diagnostics-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))),
    [string]$EnvironmentName = 'fieldora-v5'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Get-ComputerInfo | Out-File (Join-Path $OutputDirectory 'computer-info.txt') -Encoding utf8
$PSVersionTable | Out-String | Out-File (Join-Path $OutputDirectory 'powershell.txt') -Encoding utf8
Get-Command conda -ErrorAction SilentlyContinue | Format-List * | Out-File (Join-Path $OutputDirectory 'conda-command.txt') -Encoding utf8
& python (Join-Path $PSScriptRoot 'deployment_preflight.py') --release-root $root --output (Join-Path $OutputDirectory 'deployment-preflight.json') 2>&1 | Out-File (Join-Path $OutputDirectory 'deployment-preflight.log') -Encoding utf8
& conda env list --json 2>&1 | Out-File (Join-Path $OutputDirectory 'conda-environments.json') -Encoding utf8
& conda run --no-capture-output -n $EnvironmentName python (Join-Path $PSScriptRoot 'verify_install.py') 2>&1 | Out-File (Join-Path $OutputDirectory 'installed-runtime.json') -Encoding utf8
$installation = Join-Path $root '.installation'
if (Test-Path -LiteralPath $installation) { Copy-Item -LiteralPath $installation -Destination (Join-Path $OutputDirectory 'installation') -Recurse -Force }
$archive = "$OutputDirectory.zip"
Compress-Archive -LiteralPath (Join-Path $OutputDirectory '*') -DestinationPath $archive -Force
Write-Host 'The bundle does not collect libraries or photographs.' -ForegroundColor Yellow
Write-Host "Diagnostics bundle: $archive" -ForegroundColor Green
