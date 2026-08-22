[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [ValidateSet('Report', 'Caches', 'Complete')]
    [string]$Mode = 'Report',
    [string]$DataRoot,
    [switch]$IncludeSharedModelCaches,
    [switch]$Force,
    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Normalize-Path([string]$Path) {
    if (-not $Path) { return $null }
    try { return [System.IO.Path]::GetFullPath($Path).TrimEnd('\') } catch { return $Path.TrimEnd('\') }
}

function Get-DirectorySize([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return [int64]0 }
    $sum = [int64]0
    Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { $sum += [int64]$_.Length }
    return $sum
}

function Add-Candidate {
    param([string]$Path, [string]$Category, [bool]$Shared = $false)
    if (-not $Path) { return }
    $normalized = Normalize-Path $Path
    if (-not (Test-Path -LiteralPath $normalized)) { return }
    if ($script:CurrentDataRoot -and $normalized.Equals($script:CurrentDataRoot, [StringComparison]::OrdinalIgnoreCase)) { return }
    if ($script:Seen.ContainsKey($normalized)) { return }
    $script:Seen[$normalized] = $true
    $script:Candidates += [pscustomobject]@{
        path = $normalized
        category = $Category
        shared = $Shared
        bytes = Get-DirectorySize $normalized
        selected = $false
        removed = $false
        error = $null
    }
}

$script:CurrentDataRoot = Normalize-Path ($(if ($DataRoot) { $DataRoot } elseif ($env:APERTURE_DATA_ROOT) { $env:APERTURE_DATA_ROOT } elseif ($env:NATUREAI_DATA_ROOT) { $env:NATUREAI_DATA_ROOT } else { $null }))
$script:Candidates = @()
$script:Seen = @{}

# Application-owned roots used by historical Aperture/NatureAI builds.
Add-Candidate (Join-Path $env:LOCALAPPDATA 'Aperture') 'application'
Add-Candidate (Join-Path $env:LOCALAPPDATA 'NatureAI') 'application'
Add-Candidate (Join-Path $env:LOCALAPPDATA 'NatureAI Next') 'application'
Add-Candidate (Join-Path $env:APPDATA 'Aperture') 'application'
Add-Candidate (Join-Path $env:APPDATA 'NatureAI') 'application'
Add-Candidate (Join-Path $env:APPDATA 'NatureAI Next') 'application'
if ($env:PROGRAMDATA) {
    Add-Candidate (Join-Path $env:PROGRAMDATA 'Aperture') 'application'
    Add-Candidate (Join-Path $env:PROGRAMDATA 'NatureAI') 'application'
}

# Temporary files are safe cache cleanup candidates.
Get-ChildItem -LiteralPath $env:TEMP -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'Aperture*' -or $_.Name -like 'NatureAI*' } |
    ForEach-Object { Add-Candidate $_.FullName 'temporary' }

# These caches can be shared by unrelated Python projects, so deletion is opt-in.
Add-Candidate (Join-Path $env:USERPROFILE '.cache\huggingface') 'shared-model-cache' $true
Add-Candidate (Join-Path $env:USERPROFILE '.cache\torch') 'shared-model-cache' $true
Add-Candidate (Join-Path $env:LOCALAPPDATA 'huggingface') 'shared-model-cache' $true
Add-Candidate (Join-Path $env:LOCALAPPDATA 'torch') 'shared-model-cache' $true

foreach ($candidate in $script:Candidates) {
    $candidate.selected = switch ($Mode) {
        'Report' { $false }
        'Caches' { $candidate.category -eq 'temporary' -or ($IncludeSharedModelCaches -and $candidate.shared) }
        'Complete' { -not $candidate.shared -or $IncludeSharedModelCaches }
    }
}

$totalBytes = [int64](($script:Candidates | Measure-Object -Property bytes -Sum).Sum)
$selectedBytes = [int64](($script:Candidates | Where-Object selected | Measure-Object -Property bytes -Sum).Sum)
Write-Host "Aperture legacy-data scan" -ForegroundColor Cyan
Write-Host "Current data root: $(if ($script:CurrentDataRoot) {$script:CurrentDataRoot} else {'not supplied'})"
Write-Host "Mode: $Mode"
foreach ($candidate in $script:Candidates) {
    $mark = if ($candidate.selected) { '[selected]' } else { '[found]' }
    $size = '{0:N2} GB' -f ($candidate.bytes / 1GB)
    Write-Host ("{0,-10} {1,10}  {2}  ({3})" -f $mark, $size, $candidate.path, $candidate.category)
}
Write-Host ("Found: {0:N2} GB; selected: {1:N2} GB" -f ($totalBytes / 1GB), ($selectedBytes / 1GB))

if ($Mode -ne 'Report' -and $selectedBytes -ge 0) {
    if (-not $Force) {
        $answer = Read-Host 'Type DELETE to remove the selected legacy data'
        if ($answer -cne 'DELETE') { Write-Host 'No data removed.'; $Mode = 'Report' }
    }
    if ($Mode -ne 'Report') {
        foreach ($candidate in $script:Candidates | Where-Object selected) {
            try {
                if ($PSCmdlet.ShouldProcess($candidate.path, 'Remove legacy Aperture/NatureAI data')) {
                    Remove-Item -LiteralPath $candidate.path -Recurse -Force -ErrorAction Stop
                    $candidate.removed = $true
                }
            } catch {
                $candidate.error = $_.Exception.Message
                Write-Warning "Could not remove $($candidate.path): $($candidate.error)"
            }
        }
    }
}

if (-not $ReportPath) {
    $base = if ($script:CurrentDataRoot) { Join-Path $script:CurrentDataRoot 'logs' } else { Join-Path $env:TEMP 'Aperture' }
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $ReportPath = Join-Path $base ('legacy-cleanup-{0:yyyyMMdd-HHmmss}.json' -f (Get-Date))
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath) | Out-Null
}
[pscustomobject]@{
    schema_version = 1
    generated_at = (Get-Date).ToString('o')
    mode = $Mode
    current_data_root = $script:CurrentDataRoot
    include_shared_model_caches = [bool]$IncludeSharedModelCaches
    total_found_bytes = $totalBytes
    selected_bytes = $selectedBytes
    candidates = $script:Candidates
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Report: $ReportPath" -ForegroundColor Green
