"""Build and verify deterministic Aperture release manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_NAME = "RELEASE_MANIFEST.json"
_EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".installation",
    ".mypy_cache",
    ".pytest_cache",
    "pytest-of-root",
    ".ruff_cache",
    "__pycache__",
}
_EXCLUDED_SUFFIXES = {".log", ".pyc", ".pyo", ".tmp"}
_EXCLUDED_NAMES = {
    MANIFEST_NAME,
    "preflight.json",
    "deployment-preflight.json",
    "release-candidate-check.json",
    ".DS_Store",
    "Thumbs.db",
}
_VOLATILE_PATHS = {
    "preflight.json",
    "deployment-preflight.json",
    "release-candidate-check.json",
    ".installation/deployment-preflight.json",
}

_RUNTIME_PREFIXES = (
    # The default Windows data root lives beside the extracted release. It is
    # mutable installation state, never part of the immutable release package.
    "ApertureData/",
    "FieldoraData-V5/",
)


@dataclass(frozen=True)
class ManifestVerification:
    passed: bool
    expected_count: int
    manifest_count: int
    failures: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_relative(path: Path) -> str:
    return path.as_posix().removeprefix("./")


def is_release_file(relative: str) -> bool:
    normalized = normalize_relative(Path(relative))
    pure = PurePosixPath(normalized)
    if not normalized or pure.name in _EXCLUDED_NAMES:
        return False
    if any(part in _EXCLUDED_PARTS for part in pure.parts):
        return False
    if pure.suffix.lower() in _EXCLUDED_SUFFIXES:
        return False
    return not normalized.startswith(_RUNTIME_PREFIXES)


def collect_release_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and is_release_file(normalize_relative(path.relative_to(root))):
            files.append(path)
    return sorted(files, key=lambda item: normalize_relative(item.relative_to(root)).casefold())


def build_manifest(root: Path, *, version: str, build: str) -> dict[str, Any]:
    entries = []
    for path in collect_release_files(root):
        entries.append(
            {
                "path": normalize_relative(path.relative_to(root)),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"version": version, "build": build, "files": entries}


def write_manifest(root: Path, *, version: str, build: str) -> Path:
    destination = root / MANIFEST_NAME
    manifest = build_manifest(root, version=version, build=build)
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return destination


def verify_manifest(root: Path, manifest: dict[str, Any]) -> ManifestVerification:
    expected = {
        normalize_relative(path.relative_to(root)): path for path in collect_release_files(root)
    }
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return ManifestVerification(False, len(expected), 0, ("manifest files must be a list",))

    failures: list[str] = []
    recorded: dict[str, dict[str, Any]] = {}
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            failures.append("invalid manifest entry")
            continue
        relative = normalize_relative(Path(str(raw_entry.get("path", ""))))
        if relative in _VOLATILE_PATHS or relative.startswith(".installation/"):
            continue
        if not relative or not is_release_file(relative):
            failures.append(f"disallowed:{relative or '<empty>'}")
            continue
        if relative in recorded:
            failures.append(f"duplicate:{relative}")
            continue
        recorded[relative] = raw_entry

    for relative, path in expected.items():
        entry = recorded.get(relative)
        if entry is None:
            failures.append(f"unmanifested:{relative}")
            continue
        if entry.get("size") != path.stat().st_size:
            failures.append(f"size:{relative}")
        if entry.get("sha256") != sha256_file(path):
            failures.append(f"sha256:{relative}")

    for relative in sorted(set(recorded) - set(expected)):
        failures.append(f"missing:{relative}")

    return ManifestVerification(
        passed=not failures and len(recorded) == len(expected),
        expected_count=len(expected),
        manifest_count=len(recorded),
        failures=tuple(failures),
    )
