from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from release_candidate_check import validate
from release_manifest import build_manifest, verify_manifest


def _minimal_release(root: Path) -> None:
    files = {
        "VERSION": "4.0.0.dev1\n",
        "pyproject.toml": '[project]\nname="natureai-next"\nversion="4.0.0.dev1"\n',
        "RELEASE_NOTES.md": "# Build 21\nClean-start release; migration is out of scope.\n",
        "src/natureai_next/__init__.py": '__version__ = "4.0.0.dev1"\n',
        "Install Aperture.cmd": "@echo off\n",
        "Repair Aperture.cmd": "@echo off\n",
        "Uninstall Aperture.cmd": "@echo off\n",
        "scripts/install_windows.ps1": "",
        "scripts/uninstall_windows.ps1": "",
        "scripts/start_natureai_next_debug.bat": "",
        "scripts/verify_install.py": "",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_manifest_is_exact_and_excludes_runtime_files(tmp_path: Path) -> None:
    _minimal_release(tmp_path)
    runtime = tmp_path / "ApertureData/logs/session.log"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("not packaged", encoding="utf-8")
    manifest = build_manifest(tmp_path, version="4.0.0.dev1", build="build21")
    paths = {entry["path"] for entry in manifest["files"]}
    assert "ApertureData/logs/session.log" not in paths
    assert verify_manifest(tmp_path, manifest).passed

    unexpected = tmp_path / "unexpected.txt"
    unexpected.write_text("new", encoding="utf-8")
    result = verify_manifest(tmp_path, manifest)
    assert not result.passed
    assert "unmanifested:unexpected.txt" in result.failures


def test_release_candidate_check_rejects_runtime_artifacts(tmp_path: Path) -> None:
    _minimal_release(tmp_path)
    manifest = build_manifest(tmp_path, version="4.0.0.dev1", build="build21")
    (tmp_path / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert validate(tmp_path)["passed"]

    log = tmp_path / "ApertureData/logs/runtime.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{}\n", encoding="utf-8")
    report = validate(tmp_path)
    assert not report["passed"]
    failed = {check["name"] for check in report["checks"] if not check["passed"]}
    assert "no_runtime_artifacts" in failed
