"""Validation for the unified Fieldora platform bootstrap manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEPLOYMENT_TARGETS = {
    "windows-desktop",
    "linux-desktop",
    "windows-docker",
    "linux-docker",
    "kubernetes",
    "openshift",
}
_COMPONENTS = {"fieldora", "bastion", "keycloak", "wazuh", "openkat"}
_IDENTITY_PROVIDERS = {"entra", "google", "aws", "oidc", "saml"}
_REQUIRED_SUPPLY_CHAIN = {"renovate", "trivy", "syft", "osv"}
_FORBIDDEN_SECRET_VALUES = {
    "admin",
    "changeme",
    "change-me",
    "password",
    "secret",
    "fieldora",
}


class PlatformManifestError(ValueError):
    """Raised when a platform bootstrap manifest violates the installation contract."""


@dataclass(frozen=True, slots=True)
class PlatformBootstrapManifest:
    """Validated bootstrap manifest used by target-specific installers."""

    deployment_target: str
    enabled_components: tuple[str, ...]
    identity_providers: tuple[str, ...]


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlatformManifestError(f"{name} must be an object")
    return value


def _validate_secret(secret: object, name: str) -> None:
    entry = _object(secret, name)
    source = entry.get("source")
    if source == "environment":
        variable = entry.get("name")
        if not isinstance(variable, str) or not variable.strip():
            raise PlatformManifestError(f"{name}.name must identify an environment variable")
        if "value" in entry:
            raise PlatformManifestError(f"{name} cannot contain both environment and inline values")
        return
    if source != "inline":
        raise PlatformManifestError(f"{name}.source must be 'inline' or 'environment'")
    value = entry.get("value")
    if not isinstance(value, str) or len(value) < 16:
        raise PlatformManifestError(f"{name}.value must contain at least 16 characters")
    if value.strip().lower() in _FORBIDDEN_SECRET_VALUES:
        raise PlatformManifestError(f"{name}.value uses a forbidden default credential")


def validate_platform_manifest(payload: object) -> PlatformBootstrapManifest:
    """Validate one unified bootstrap payload without persisting or logging secrets."""
    root = _object(payload, "manifest")
    if root.get("schema_version") != 1:
        raise PlatformManifestError("schema_version must be 1")

    target = root.get("deployment_target")
    if target not in _DEPLOYMENT_TARGETS:
        raise PlatformManifestError("deployment_target is not a supported Fieldora target")

    components = _object(root.get("components"), "components")
    unknown_components = set(components) - _COMPONENTS
    if unknown_components:
        raise PlatformManifestError(
            f"unknown components: {', '.join(sorted(unknown_components))}"
        )
    enabled: list[str] = []
    for component in sorted(_COMPONENTS):
        config = _object(components.get(component), f"components.{component}")
        if not isinstance(config.get("enabled"), bool):
            raise PlatformManifestError(f"components.{component}.enabled must be boolean")
        if config["enabled"]:
            enabled.append(component)
            version = config.get("version")
            if not isinstance(version, str) or not version.strip():
                raise PlatformManifestError(
                    f"components.{component}.version is required when enabled"
                )
    if "fieldora" not in enabled:
        raise PlatformManifestError("Fieldora must be enabled")

    administrators = _object(root.get("administrators"), "administrators")
    for component in ("fieldora", "keycloak", "wazuh", "openkat"):
        if component not in enabled:
            continue
        admin = _object(administrators.get(component), f"administrators.{component}")
        username = admin.get("username")
        if not isinstance(username, str) or not username.strip():
            raise PlatformManifestError(f"administrators.{component}.username is required")
        _validate_secret(admin.get("password"), f"administrators.{component}.password")

    secrets = _object(root.get("secrets"), "secrets")
    for name in ("fieldora_service", "bastion_service"):
        if name == "bastion_service" and "bastion" not in enabled:
            continue
        _validate_secret(secrets.get(name), f"secrets.{name}")

    identity = _object(root.get("identity"), "identity")
    brokers = identity.get("brokers", [])
    if not isinstance(brokers, list):
        raise PlatformManifestError("identity.brokers must be an array")
    providers: list[str] = []
    for index, broker_value in enumerate(brokers):
        broker = _object(broker_value, f"identity.brokers[{index}]")
        provider = broker.get("provider")
        if provider not in _IDENTITY_PROVIDERS:
            raise PlatformManifestError(
                f"identity.brokers[{index}].provider is not supported"
            )
        providers.append(provider)
        client_id = broker.get("client_id")
        if not isinstance(client_id, str) or not client_id.strip():
            raise PlatformManifestError(f"identity.brokers[{index}].client_id is required")
        _validate_secret(
            broker.get("client_secret"), f"identity.brokers[{index}].client_secret"
        )
    if providers and "keycloak" not in enabled:
        raise PlatformManifestError("identity brokers require Keycloak to be enabled")

    supply_chain = _object(root.get("supply_chain"), "supply_chain")
    for tool in sorted(_REQUIRED_SUPPLY_CHAIN):
        if supply_chain.get(tool) is not True:
            raise PlatformManifestError(f"supply_chain.{tool} must be enabled")
    if supply_chain.get("license_policy") != "commercial-private":
        raise PlatformManifestError(
            "supply_chain.license_policy must be 'commercial-private'"
        )

    return PlatformBootstrapManifest(
        deployment_target=target,
        enabled_components=tuple(enabled),
        identity_providers=tuple(providers),
    )


def load_platform_manifest(path: str | Path) -> PlatformBootstrapManifest:
    """Load and validate a JSON bootstrap manifest from disk."""
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlatformManifestError(f"cannot load platform manifest: {exc}") from exc
    return validate_platform_manifest(payload)
