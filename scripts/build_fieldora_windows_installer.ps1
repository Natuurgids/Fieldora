[CmdletBinding()]
param(
    [ValidateSet('GUI', 'FullAI')]
    [string]$BuildProfile = 'GUI',
    [string]$Version = '',
    [string]$EnvironmentName = 'fieldora-build',
    [string]$DefaultLibrary = '',
    [switch]$SkipTests,
    [switch]$Clean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LegacyBuilder = Join-Path $PSScriptRoot 'build_aperture_windows_installer.ps1'
$PyProject = Join-Path $RepositoryRoot 'pyproject.toml'
if (-not (Test-Path -LiteralPath $LegacyBuilder -PathType Leaf)) { throw "Installer builder not found: $LegacyBuilder" }
if (-not (Test-Path -LiteralPath $PyProject -PathType Leaf)) { throw "pyproject.toml not found: $PyProject" }

if ([string]::IsNullOrWhiteSpace($Version)) {
    $match = [regex]::Match((Get-Content -LiteralPath $PyProject -Raw), '(?m)^version\s*=\s*"([^"]+)"')
    if (-not $match.Success) { throw 'Unable to derive Fieldora version from pyproject.toml.' }
    $Version = $match.Groups[1].Value
}

# The historical builder derives its repository root from PSScriptRoot. Execute an
# exact temporary copy from repository root so that its existing packaging contract
# resolves pyproject.toml and src/natureai_next correctly without duplicating it.
$TemporaryBuilder = Join-Path $RepositoryRoot '.fieldora-windows-installer-build.ps1'
Copy-Item -LiteralPath $LegacyBuilder -Destination $TemporaryBuilder -Force
try {
    $invoke = @{
        BuildProfile = $BuildProfile
        Version = $Version
        EnvironmentName = $EnvironmentName
        DefaultLibrary = $DefaultLibrary
    }
    if ($SkipTests) { $invoke.SkipTests = $true }
    if ($Clean) { $invoke.Clean = $true }
    & $TemporaryBuilder @invoke
    if ($LASTEXITCODE -ne 0) { throw "Fieldora Windows installer build failed with exit code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath $TemporaryBuilder -Force -ErrorAction SilentlyContinue
}

$setup = Join-Path $RepositoryRoot "dist-installer\Fieldora-$Version-Setup.exe"
$hash = "$setup.sha256"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) { throw "Expected installer was not produced: $setup" }
if (-not (Test-Path -LiteralPath $hash -PathType Leaf)) { throw "Expected installer hash was not produced: $hash" }
Write-Host "Fieldora Windows review installer: $setup" -ForegroundColor Green
Write-Host "SHA-256 file: $hash"