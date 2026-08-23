from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.bootstrap.platform_server_cli import _storage_service_listener
from natureai_next.server.storage_service_runtime import StorageServiceListenerConfig


def test_storage_listener_is_disabled_unless_explicitly_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIELDORA_STORAGE_SERVICE_ENABLED", raising=False)
    assert _storage_service_listener(["serve"], "serve") is None


def test_storage_listener_requires_postgres_science(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDORA_STORAGE_SERVICE_ENABLED", "true")
    with pytest.raises(SystemExit, match="science-backend postgresql"):
        _storage_service_listener(["serve", "--science-backend", "sqlite"], "serve")


def test_storage_listener_requires_postgres_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDORA_STORAGE_SERVICE_ENABLED", "true")
    with pytest.raises(SystemExit, match="governance-backend postgresql"):
        _storage_service_listener(
            ["serve", "--science-backend", "postgresql", "--governance-backend", "sqlite"],
            "serve",
        )


def test_listener_config_rejects_missing_tls_material(tmp_path: Path) -> None:
    config = StorageServiceListenerConfig(
        host="127.0.0.1",
        port=8766,
        certificate=tmp_path / "server.pem",
        private_key=tmp_path / "server-key.pem",
        client_ca=tmp_path / "ca.pem",
    )
    with pytest.raises(ValueError, match="certificate"):
        config.validate()


def test_listener_config_accepts_complete_tls_material(tmp_path: Path) -> None:
    certificate = tmp_path / "server.pem"
    private_key = tmp_path / "server-key.pem"
    client_ca = tmp_path / "ca.pem"
    for path in (certificate, private_key, client_ca):
        path.write_text("test", encoding="utf-8")
    config = StorageServiceListenerConfig(
        host="127.0.0.1",
        port=8766,
        certificate=certificate,
        private_key=private_key,
        client_ca=client_ca,
    )
    config.validate()
