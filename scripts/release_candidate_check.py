"""Consolidated, non-mutating release-candidate checks for Aperture."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from release_manifest import MANIFEST_NAME, verify_manifest


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


def _project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def _module_version(root: Path) -> str:
    text = (root / "src/natureai_next/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, flags=re.MULTILINE)
    if not match:
        raise ValueError("__version__ is missing")
    return match.group(1)


def validate(root: Path) -> dict[str, object]:
    checks: list[Check] = []
    required = (
        "VERSION",
        "pyproject.toml",
        "RELEASE_NOTES.md",
        MANIFEST_NAME,
        "Install Aperture.cmd",
        "Repair Aperture.cmd",
        "Uninstall Aperture.cmd",
        "scripts/install_windows.ps1",
        "scripts/uninstall_windows.ps1",
        "scripts/start_natureai_next_debug.bat",
        "scripts/verify_install.py",
    )
    for relative in required:
        checks.append(Check(f"required:{relative}", (root / relative).is_file(), relative))

    try:
        versions = {
            "VERSION": (root / "VERSION").read_text(encoding="utf-8").strip(),
            "pyproject": _project_version(root),
            "module": _module_version(root),
        }
        checks.append(
            Check("version_consistency", len(set(versions.values())) == 1, json.dumps(versions))
        )
    except Exception as exc:
        checks.append(Check("version_consistency", False, str(exc)))

    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        result = verify_manifest(root, manifest)
        checks.append(
            Check(
                "manifest_exact",
                result.passed,
                f"{result.manifest_count}/{result.expected_count}; "
                + (", ".join(result.failures[:12]) or "all packaged files verified"),
            )
        )
    except Exception as exc:
        checks.append(Check("manifest_exact", False, str(exc)))

    runtime_artifacts = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(
            (
                "ApertureData/logs/",
                "ApertureData/cache/",
                "ApertureData/tmp/",
                "FieldoraData-V5/logs/",
                "FieldoraData-V5/cache/",
                "FieldoraData-V5/tmp/",
            )
        ) or path.suffix.lower() in {".pyc", ".pyo", ".log", ".tmp"}:
            runtime_artifacts.append(relative)
    checks.append(
        Check(
            "no_runtime_artifacts",
            not runtime_artifacts,
            ", ".join(runtime_artifacts[:12]) or "clean release tree",
        )
    )

    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    clean_start = "clean-start" in notes.lower() and "migration" in notes.lower()
    checks.append(Check("clean_start_scope_declared", clean_start, "release notes declare scope"))

    return {
        "product": "Fieldora",
        "release_root": str(root.resolve()),
        "checks": [asdict(check) for check in checks],
        "passed": all(check.passed for check in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(args.release_root)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
