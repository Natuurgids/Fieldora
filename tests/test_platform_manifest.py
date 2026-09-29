import copy

import pytest

from natureai_next.bootstrap.platform_manifest import (
    PlatformManifestError,
    validate_platform_manifest,
)


def _secret(value: str) -> dict[str, str]:
    return {"source": "inline", "value": value}


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "deployment_target": "linux-docker",
        "components": {
            "fieldora": {"enabled": True, "version": "5.4.0"},
            "bastion": {"enabled": True, "version": "1.0.0"},
            "keycloak": {"enabled": True, "version": "approved"},
            "wazuh": {"enabled": True, "version": "approved"},
            "openkat": {"enabled": False, "version": "approved"},
        },
        "administrators": {
            "fieldora": {"username": "admin", "password": _secret("fieldora-admin-strong-1")},
            "keycloak": {"username": "kc-admin", "password": _secret("keycloak-admin-strong-1")},
            "wazuh": {"username": "wazuh-admin", "password": _secret("wazuh-admin-strong-1")},
        },
        "secrets": {
            "fieldora_service": _secret("fieldora-service-strong-1"),
            "bastion_service": _secret("bastion-service-strong-1"),
        },
        "identity": {
            "brokers": [
                {
                    "provider": "entra",
                    "client_id": "fieldora",
                    "client_secret": _secret("entra-client-secret-strong-1"),
                }
            ]
        },
        "supply_chain": {
            "renovate": True,
            "trivy": True,
            "syft": True,
            "osv": True,
            "license_policy": "commercial-private",
        },
    }


def test_valid_manifest_returns_bounded_non_secret_summary() -> None:
    manifest = validate_platform_manifest(_manifest())
    assert manifest.deployment_target == "linux-docker"
    assert manifest.enabled_components == ("bastion", "fieldora", "keycloak", "wazuh")
    assert manifest.identity_providers == ("entra",)
    assert "password" not in repr(manifest)
    assert "secret" not in repr(manifest).lower()


def test_all_first_class_targets_are_accepted() -> None:
    for target in (
        "windows-desktop",
        "linux-desktop",
        "windows-docker",
        "linux-docker",
        "kubernetes",
        "openshift",
    ):
        payload = _manifest()
        payload["deployment_target"] = target
        assert validate_platform_manifest(payload).deployment_target == target


def test_identity_broker_requires_keycloak() -> None:
    payload = _manifest()
    components = payload["components"]
    assert isinstance(components, dict)
    components["keycloak"] = {"enabled": False, "version": "approved"}
    with pytest.raises(PlatformManifestError, match="require Keycloak"):
        validate_platform_manifest(payload)


def test_short_or_default_inline_password_is_rejected() -> None:
    payload = _manifest()
    administrators = payload["administrators"]
    assert isinstance(administrators, dict)
    fieldora = administrators["fieldora"]
    assert isinstance(fieldora, dict)
    fieldora["password"] = _secret("password")
    with pytest.raises(PlatformManifestError, match="at least 16 characters"):
        validate_platform_manifest(payload)


def test_environment_secret_reference_is_accepted_without_inline_value() -> None:
    payload = _manifest()
    secrets = payload["secrets"]
    assert isinstance(secrets, dict)
    secrets["fieldora_service"] = {"source": "environment", "name": "FIELDORA_SERVICE_SECRET"}
    assert validate_platform_manifest(payload).deployment_target == "linux-docker"


def test_supply_chain_security_and_license_controls_cannot_be_disabled() -> None:
    for key in ("renovate", "trivy", "syft", "osv"):
        payload = copy.deepcopy(_manifest())
        supply_chain = payload["supply_chain"]
        assert isinstance(supply_chain, dict)
        supply_chain[key] = False
        with pytest.raises(PlatformManifestError, match=key):
            validate_platform_manifest(payload)

    payload = _manifest()
    supply_chain = payload["supply_chain"]
    assert isinstance(supply_chain, dict)
    supply_chain["license_policy"] = "permissive"
    with pytest.raises(PlatformManifestError, match="commercial-private"):
        validate_platform_manifest(payload)
