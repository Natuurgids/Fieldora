from __future__ import annotations

import hashlib
import json

import pytest

from natureai_next.application.updates import OfflineUpdateService, UpdateCandidate
from natureai_next.bootstrap import native_updater


class _SilentProgress:
    def __init__(self, current: str, target: str) -> None:
        pass

    def pump(self) -> None:
        pass

    def stage(self, text: str, progress: int) -> None:
        pass

    def failure(self, text: str) -> None:
        pass

    def success(self, version: str) -> None:
        pass


def test_native_helper_refuses_missing_security_install_before_pip(tmp_path, monkeypatch) -> None:
    package = tmp_path / "fieldora.whl"
    package.write_bytes(b"wheel")
    request = tmp_path / "pending-update.json"
    request.write_text(
        json.dumps(
            {
                "format": "natureai-next.pending-update",
                "format_version": 1,
                "product": "Fieldora",
                "from_version": "5.4.0",
                "version": "5.5.0",
                "package": package.name,
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                "status": "staged",
            }
        ),
        encoding="utf-8",
    )
    calls: list[object] = []
    monkeypatch.setattr(native_updater, "_ProgressUI", _SilentProgress)
    monkeypatch.setattr(native_updater.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ValueError, match="Security Install evidence"):
        native_updater.main(
            ["--request", str(request), "--parent-pid", "999999", "--library", str(tmp_path)]
        )

    assert calls == []


def test_update_staging_fails_closed_without_security_install_evidence(tmp_path) -> None:
    package = tmp_path / "fieldora.whl"
    package.write_bytes(b"wheel")
    candidate = UpdateCandidate(
        product="Fieldora",
        version="5.5.0",
        minimum_supported_version="5.4.0",
        package_path=package,
        sha256=hashlib.sha256(package.read_bytes()).hexdigest(),
        release_notes="",
    )

    with pytest.raises(ValueError, match="Security Install evidence"):
        OfflineUpdateService(current_version="5.4.0").stage(candidate, tmp_path / "staged")
