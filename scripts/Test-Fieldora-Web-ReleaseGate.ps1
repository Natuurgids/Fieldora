<#
Fail-closed WEB-060 release gate for managed-web functional parity.

This validator does not perform runtime certification. It consumes the bounded proof emitted
by Certify-Fieldora-Clean-Runtime.ps1 and the authoritative parity plan. A release is accepted
only when every mandatory WEB-001..WEB-059 row is explicitly DONE and the Windows 11 proof
belongs to the exact supplied Fieldora commit.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$FieldoraRef,
    [Parameter(Mandatory=$true)]
    [string]$WindowsProofPath,
    [string]$ParityPlanPath = './WEB_DESKTOP_PARITY_PLAN.md'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

Require (Test-Path -LiteralPath $ParityPlanPath -PathType Leaf) "Parity plan is missing: $ParityPlanPath"
$plan = Get-Content -LiteralPath $ParityPlanPath
$statusById = @{}
foreach ($line in $plan) {
    if ($line -match '^\| WEB-(\d{3}) \| ([A-Z]+) \|') {
        $statusById[[int]$matches[1]] = $matches[2]
    }
}
$notDone = @()
foreach ($id in 1..59) {
    if (-not $statusById.ContainsKey($id)) {
        $notDone += ('WEB-{0:D3}:missing' -f $id)
    }
    elseif ($statusById[$id] -ne 'DONE') {
        $notDone += ('WEB-{0:D3}:{1}' -f $id, $statusById[$id])
    }
}
Require ($notDone.Count -eq 0) ("Mandatory web parity work is incomplete: " + ($notDone -join ', '))

Require (Test-Path -LiteralPath $WindowsProofPath -PathType Leaf) "Windows runtime proof is missing: $WindowsProofPath"
$proof = Get-Content -LiteralPath $WindowsProofPath -Raw | ConvertFrom-Json

Require ($proof.schema -eq 'fieldora.clean-runtime-certification.v1') 'Unexpected runtime proof schema.'
Require ($proof.fieldora_ref -eq $FieldoraRef.ToLowerInvariant()) 'Runtime proof does not match the exact Fieldora commit.'
Require ($proof.platform -eq 'Windows11') 'WEB-060 requires a Windows11 Docker runtime proof.'
Require ([string]$proof.host_identity -match '^Windows ') 'Runtime proof host identity is not Windows.'
Require ([string]$proof.install_root -eq 'D:\FDTEST') 'Windows runtime proof must be pinned to D:\FDTEST.'
Require (-not [bool]$proof.secrets_or_payloads_recorded) 'Runtime proof reports recorded secrets or payloads.'
Require ([bool]$proof.credential_handoff.present) 'Temporary administrator credential handoff was not verified.'
Require (-not [bool]$proof.credential_handoff.content_recorded) 'Runtime proof must not record administrator credential content.'
Require ([bool]$proof.storage_service_mtls_desired_state) 'Storage-service mTLS desired state was not verified.'

foreach ($name in @('live','ready','openapi','root','docs')) {
    Require ([bool]$proof.https.$name) "HTTPS runtime check failed or is missing: $name"
}

$requiredServices = @('fieldora-postgres','fieldora-server','fieldora-worker','fieldora-cert-renewer')
$services = @{}
foreach ($service in @($proof.services)) {
    $services[[string]$service.name] = $service
}
foreach ($name in $requiredServices) {
    Require ($services.ContainsKey($name)) "Required runtime service is missing from proof: $name"
    Require ([bool]$services[$name].running) "Required runtime service is not running: $name"
    Require ([int]$services[$name].restart_count -eq 0) "Required runtime service restarted during certification: $name"
}

$started = [DateTimeOffset]::Parse([string]$proof.started_at)
$completed = [DateTimeOffset]::Parse([string]$proof.completed_at)
Require ($completed -ge $started) 'Runtime proof completion timestamp precedes its start timestamp.'
Require (-not [string]::IsNullOrWhiteSpace([string]$proof.docker_server_version)) 'Docker server version is missing from runtime proof.'
Require (-not [string]::IsNullOrWhiteSpace([string]$proof.docker_compose_version)) 'Docker Compose version is missing from runtime proof.'

Write-Host 'WEB-060 WINDOWS FUNCTIONAL-PARITY RELEASE GATE PASSED' -ForegroundColor Green
