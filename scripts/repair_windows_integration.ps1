[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$EnvironmentName = 'fieldora-v5',
    [string]$DefaultLibrary
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install_windows.ps1'
$arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer,
    '-EnvironmentName', $EnvironmentName,
    '-InstallProfile', 'Core',
    '-RecreateEnvironment:$false',
    '-SkipDependencyInstallation',
    '-SkipPackageInstallation',
    '-SkipSmokeTest'
)
if ($DefaultLibrary) { $arguments += @('-DefaultLibrary', $DefaultLibrary) }
& powershell.exe @arguments
exit $LASTEXITCODE
