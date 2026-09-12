from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Start-Fieldora-LinkedStorage.ps1"


def test_startup_helper_consumes_trust_handoff_and_opaque_storage_identity() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'Join-Path $trustFull "HANDOFF.json"' in text
    assert '([string]$handoff.service_id).Trim()' in text
    assert '([string]$handoff.organization_id).Trim()' in text
    assert '[Guid]::TryParseExact($serviceId, "D"' in text
    assert 'Assert-Opaque "StorageId" $StorageId' in text
    assert 'Assert-Opaque "RootAlias" $RootAlias' in text
    assert 'FIELDORA_STORAGE_SERVICE_ID' in text
    assert 'FIELDORA_STORAGE_ORGANIZATION' in text


def test_startup_helper_uses_private_same_host_network_and_https_by_default() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '[string]$Endpoint = "https://fieldora-server:8765"' in text
    assert '[string]$PlatformNetwork = "fieldora_fieldora-network"' in text
    assert 'compose.same-host.yaml' in text
    assert '$parsedEndpoint.Scheme -ne "https"' in text
    assert 'docker network ls --filter "name=^${PlatformNetwork}$"' in text
    assert 'FIELDORA_PLATFORM_NETWORK' in text


def test_startup_helper_preserves_host_storage_boundary_and_read_only_compose_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    compose = (ROOT / "deployment" / "storage-node" / "compose.yaml").read_text(
        encoding="utf-8"
    )

    assert 'Test-Path -LiteralPath $storageFull -PathType Container' in text
    assert 'FIELDORA_STORAGE_ROOT = $storageFull' in text
    assert 'FIELDORA_STORAGE_TRUST_DIR = $trustFull' in text
    assert 'password' not in text.casefold()
    assert 'username' not in text.casefold()
    assert 'Invoke-WebRequest' not in text
    assert '${FIELDORA_STORAGE_ROOT:?Set FIELDORA_STORAGE_ROOT to the organisation archive path}:/mnt/fieldora-storage:ro' in compose
    assert '${FIELDORA_STORAGE_TRUST_DIR:?Set FIELDORA_STORAGE_TRUST_DIR to the enrolled service trust directory}:/run/fieldora-trust:ro' in compose


def test_startup_helper_fails_if_container_restarts_during_startup() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '{{.State.Status}}' in text
    assert '{{.RestartCount}}' in text
    assert 'if ($restartCount -ne 0)' in text
    assert 'throw "Linked storage service restarted $restartCount time(s) during startup."' in text
