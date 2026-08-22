from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.filesystem.library_manifest import read_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_windows_frontend_is_single_pass_and_passes_selected_library_once() -> None:
    text = (ROOT / "scripts/install_aperture_frontend.ps1").read_text(encoding="utf-8")
    assert text.count("& $installScript") == 1
    assert "-DefaultLibrary $libraryPath" in text
    assert "-CreateDefaultLibrary:(-not $existingLibrary)" in text
    assert "SkipPackageInstallation" not in text


def test_installer_never_invents_repository_local_library() -> None:
    text = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "Join-Path (Split-Path -Parent $DataRoot) 'Fieldora-Library-V5'" in text
    assert "Join-Path $RepositoryRoot 'ApertureLibrary-V4'" not in text


def test_manifest_read_is_strict_and_non_mutating(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    payload = {
        "format_version": 1,
        "library_public_id": "id",
        "display_name": "x",
        "created_at_us": 1,
        "database_filename": "library.sqlite3",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    assert read_manifest(path).library_public_id == "id"
    assert path.read_bytes() == before
    payload["format_version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        read_manifest(path)


def test_read_only_connection_is_physically_read_only(tmp_path: Path) -> None:
    db = tmp_path / "space # unicode-ä.sqlite3"
    c = sqlite3.connect(db)
    c.execute("create table t(x integer)")
    c.commit()
    c.close()
    ro = SqliteConnectionFactory(db).connect(read_only=True)
    try:
        assert ro.execute("select count(*) from t").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("insert into t values (1)")
    finally:
        ro.close()
