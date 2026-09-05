from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Renew-Fieldora-LinkedStorageTrust.ps1"


def test_renewal_helper_uses_only_constrained_issuer_and_local_governance_dsn() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "fieldora-issuer-authority:/authority:ro" in text
    assert "fieldora-governance-dsn" in text
    assert "fieldora-certificate-renewer" in text
    assert "--once" in text
    assert "ca-private.pem" in text
    assert "test ! -e /authority/ca-private.pem" in text
    assert "Invoke-WebRequest" not in text
    assert "curl" not in text
    assert "wget" not in text


def test_renewal_helper_preserves_durable_service_identity() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'Join-Path $trustFull "HANDOFF.json"' in text
    assert '[Guid]::TryParseExact($serviceId, "D"' in text
    assert 'service_id = $serviceId' in text
    assert 'organization_id = $organizationId' in text
    assert 'common_name = "fieldora-linked-storage"' in text
    assert 'if ($certificate.service_id -ne $serviceId -or $certificate.organization_id -ne $organizationId)' in text


def test_renewal_helper_updates_leaf_in_place_for_agent_hot_reload() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'certificate = "/target/service.crt"' in text
    assert 'private_key = "/target/service.key"' in text
    assert '-v "${trustFull}:/target"' in text
    assert '--renew-before-hours $window' in text
    assert '--lifetime-hours $LifetimeHours' in text
    assert "reloads certificate files for subsequent mTLS requests" in text
