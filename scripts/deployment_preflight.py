"""Validate an Aperture release tree before Windows deployment mutates the machine."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from release_manifest import verify_manifest
except ModuleNotFoundError:  # imported as scripts.deployment_preflight in tests/tools
    from scripts.release_manifest import verify_manifest


WINDOWS_FORBIDDEN = set('<>:"|?*')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def windows_path_failures(paths: list[str]) -> tuple[str, ...]:
    failures: list[str] = []
    for path in paths:
        for part in Path(path).parts:
            stem = part.split(".", 1)[0].upper()
            if any(character in WINDOWS_FORBIDDEN for character in part):
                failures.append(f"illegal-character:{path}")
                break
            if part.endswith((" ", ".")):
                failures.append(f"trailing-space-or-dot:{path}")
                break
            if stem in WINDOWS_RESERVED:
                failures.append(f"reserved-name:{path}")
                break
    return tuple(failures)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def validate_release(root: Path) -> dict[str, object]:
    required = (
        "pyproject.toml",
        "RELEASE_NOTES.md",
        "RELEASE_MANIFEST.json",
        "scripts/install_windows.ps1",
        "scripts/uninstall_windows.ps1",
        "scripts/verify_install.py",
        "resources/fieldora.ico",
    )
    checks = [Check(f"required:{name}", (root / name).is_file(), name) for name in required]
    version = "unknown"
    init_path = root / "src/natureai_next/__init__.py"
    if init_path.is_file():
        for line in init_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                version = line.split("=", 1)[1].strip().strip("\"'")
                break
    manifest_path = root / "RELEASE_MANIFEST.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            result = verify_manifest(root, data)
            checks.append(
                Check(
                    "release_manifest",
                    result.passed,
                    ", ".join(result.failures[:10])
                    or f"{result.manifest_count} files; exact package inventory",
                )
            )
            entries = data.get("files", [])
            path_failures = windows_path_failures(
                [str(entry.get("path", "")) for entry in entries if isinstance(entry, dict)]
            )
            checks.append(Check(
                "windows_paths",
                not path_failures,
                ", ".join(path_failures[:10]) or f"{len(entries)} manifest paths are Windows-safe",
            ))
        except Exception as exc:  # deployment report must explain malformed input
            checks.append(Check("release_manifest", False, str(exc)))
    checks.append(
        Check("bootstrap_python", sys.version_info >= (3, 9), sys.version.replace("\n", " "))
    )
    return {
        "product": "Fieldora",
        "engine": "Fieldora Engine",
        "version": version,
        "platform": platform.platform(),
        "release_root": str(root.resolve()),
        "checks": [asdict(check) for check in checks],
        "passed": all(check.passed for check in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_release(args.release_root)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
