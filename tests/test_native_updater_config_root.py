from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from natureai_next.bootstrap.native_updater import _require_trusted_update, _sha256


def test_trusted_update_uses_explicit_config_root_despite_conflicting_environment(
    tmp_path: Path, monkeypatch,
) -> None:
    config_root = tmp_path / "explicit-root"
    inherited_root = tmp_path / "attacker-controlled-root"
    request_dir = tmp_path / "staging"
    request_dir.mkdir()
    request_path = request_dir / "pending-update.json"
    package = request_dir / "fieldora.whl"
    package.write_bytes(b"signed package bytes")
    evidence = {"format": "security-install-evidence"}
    release_digest = "a" * 64
    signed = {
        "package": package.name,
        "sha256": _sha256(package),
        "size": package.stat().st_size,
        "version": "5.1.0",
        "release_id": "fieldora-5.1.0",
        "release_digest": release_digest,
        "security_install": evidence,
    }
    payload = {
        **signed,
        "from_version": "5.0.0",
        "signed_index": "signed-update-index.json",
    }
    monkeypatch.setenv("APERTURE_DATA_ROOT", str(inherited_root))
    monkeypatch.setenv("NATUREAI_DATA_ROOT", str(inherited_root))

    with (
        patch(
            "natureai_next.bootstrap.native_updater.verify_signed_update_index",
            return_value=SimpleNamespace(payload=signed, key_id="release-key"),
        ),
        patch("natureai_next.bootstrap.native_updater.require_security_install") as require,
    ):
        _require_trusted_update(
            payload,
            package,
            request_path,
            trust_anchor=config_root / "update-trust-anchors.json",
            config_root=config_root,
        )

    expected_database = (
        config_root.resolve() / "subsystems" / "access-control.sqlite3"
    )
    assert require.call_args.kwargs["access_control_database"] == expected_database
    assert inherited_root.resolve() not in expected_database.parents
