[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string]$Root = 'D:\',
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$patterns = @(
    'natureai-next-post*',
    'natureai-next-hotfix*',
    'natureai-next-old*'
)

$candidates = foreach ($pattern in $patterns) {
    Get-ChildItem -LiteralPath $Root -Directory -Filter $pattern -ErrorAction SilentlyContinue
}
$candidates = @($candidates | Sort-Object FullName -Unique)

if ($candidates.Count -eq 0) {
    Write-Host 'No old NatureAI Next extraction folders were found.'
    exit 0
}

Write-Host 'Candidate old extraction folders:' -ForegroundColor Cyan
$candidates | ForEach-Object { Write-Host "  $($_.FullName)" }
Write-Host ''
Write-Host 'This list deliberately excludes NatureAI-Libraries and photo folders.' -ForegroundColor Yellow

if (-not $Apply) {
    Write-Host 'Dry run only. Rerun with -Apply to request deletion.'
    exit 0
}

foreach ($candidate in $candidates) {
    if ($PSCmdlet.ShouldProcess($candidate.FullName, 'Delete old extracted build folder')) {
        Remove-Item -LiteralPath $candidate.FullName -Recurse -Force
    }
}
