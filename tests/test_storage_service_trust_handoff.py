from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "New-Fieldora-Storage-ServiceTrust.ps1"


def test_storage_trust_handoff_uses_prepared_service_id_and_constrained_issuer() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '[Parameter(Mandatory)][string]$ServiceId' in text
    assert '[Guid]::TryParseExact($ServiceId.Trim(), "D"' in text
    assert '$issuerVolume = "fieldora-issuer-authority"' in text
    assert '-v "${issuerVolume}:/authority:ro"' in text
    assert 'fieldora-service-trust --root /authority issue' in text
    assert '--service-id $canonicalServiceId' in text
    assert '--organization $organizationId' in text
    assert '--new-private-key' in text


def test_storage_trust_handoff_never_mounts_offline_root_private_key() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'test ! -e /authority/ca-private.pem' in text
    assert 'offline_root_ca_private_key_mounted = $false' in text
    assert '$authorityRoot' not in text
    assert 'cp /authority/ca-certificate.pem /output/ca-certificate.pem' in text
    assert 'Copy-Item -LiteralPath (Join-Path $authorityRoot' not in text


def test_storage_trust_handoff_exports_leaf_key_and_public_ca_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'service.crt' in text
    assert 'service.key' in text
    assert 'ca-certificate.pem' in text
    assert 'private_key_content_recorded = $false' in text
    assert 'Do not paste service.key or CA material into the browser.' in text
    assert 'issuer-private.pem /output' not in text
    assert 'ca-private.pem /output' not in text


def test_storage_trust_handoff_defaults_to_clean_install_without_wan_dependency() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '"D:\\FDTEST"' in text
    assert 'fieldora-v5-rocky:local' in text
    assert 'Join-Path "linked-storage-trust" $canonicalServiceId' in text
    assert 'Invoke-WebRequest' not in text
    assert 'curl' not in text
    assert 'wget' not in text
