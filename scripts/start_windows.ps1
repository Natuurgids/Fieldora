[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Library,
    [string]$EnvironmentName = 'fieldora-v5',
    [switch]$SafeMode,
    [switch]$Diagnostics,
    [ValidateSet('DEBUG', 'INFO', 'WARNING', 'ERROR')]
    [string]$LogLevel = 'INFO',
    [string]$LibraryName = 'Aperture Library',
    [string]$Locale = 'en'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# The Python launcher performs a guarded clean-start initialization when the
# selected path is absent or an empty directory. Existing non-library content
# is never modified.
$arguments = @('run', '--no-capture-output', '-n', $EnvironmentName, 'natureai-next', '--library', $Library, '--log-level', $LogLevel)
if ($SafeMode) { $arguments += '--safe-mode' }
if ($Diagnostics) { $arguments += '--diagnostics' }

& conda @arguments
exit $LASTEXITCODE
