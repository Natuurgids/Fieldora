import json
import zipfile
from pathlib import Path

from scripts.build_release_archive import build_archive
from scripts.deployment_preflight import validate_release
from scripts.release_manifest import build_manifest, is_release_file


def test_volatile_deployment_reports_are_not_release_files():
    assert not is_release_file("deployment-preflight.json")
    assert not is_release_file(".installation/deployment-preflight.json")
    assert not is_release_file("release-candidate-check.json")


def test_release_archive_contains_manifest_and_passes_after_extraction(tmp_path):
    root = tmp_path / "source"
    for relative in (
        "scripts/install_windows.ps1",
        "scripts/uninstall_windows.ps1",
        "scripts/verify_install.py",
        "resources/fieldora.ico",
        "src/natureai_next/__init__.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('__version__ = "5.3.12"\n' if relative.endswith("__init__.py") else relative, encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nversion="5.3.12"\n', encoding="utf-8")
    (root / "RELEASE_NOTES.md").write_text("Fieldora 5.3.12 clean install\n", encoding="utf-8")
    manifest = build_manifest(root, version="5.3.12", build="archive-test")
    (root / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    archive = tmp_path / "release.zip"
    build_archive(root, archive, "Fieldora-5.3.12")
    with zipfile.ZipFile(archive) as package:
        assert "Fieldora-5.3.12/RELEASE_MANIFEST.json" in package.namelist()
        package.extractall(tmp_path / "extracted")
    report = validate_release(tmp_path / "extracted/Fieldora-5.3.12")
    assert report["passed"], report
