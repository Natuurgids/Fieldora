import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from release_manifest import build_manifest

SCRIPT = SCRIPTS / "deployment_preflight.py"


def test_volatile_preflight_outputs_are_ignored(tmp_path: Path) -> None:
    required = [
        "pyproject.toml",
        "RELEASE_NOTES.md",
        "scripts/install_windows.ps1",
        "scripts/uninstall_windows.ps1",
        "scripts/verify_install.py",
        "resources/fieldora.ico",
        "src/natureai_next/__init__.py",
    ]
    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '__version__ = "3.0.0"\n' if relative.endswith("__init__.py") else "x",
            encoding="utf-8",
        )

    manifest = build_manifest(tmp_path, version="3.0.0", build="test")
    manifest["files"].extend(
        [
            {"path": "preflight.json", "size": 1, "sha256": "bad"},
            {"path": ".installation/deployment-preflight.json", "size": 1, "sha256": "bad"},
        ]
    )
    # Mutable preflight reports are not release files and must not affect verification.
    (tmp_path / "preflight.json").write_text("x", encoding="utf-8")
    installation = tmp_path / ".installation/deployment-preflight.json"
    installation.parent.mkdir(parents=True)
    installation.write_text("x", encoding="utf-8")
    (tmp_path / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--release-root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
