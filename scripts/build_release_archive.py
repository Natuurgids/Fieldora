"""Build and verify an installable Fieldora release ZIP from its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

try:
    from release_manifest import MANIFEST_NAME, verify_manifest
except ModuleNotFoundError:  # imported as scripts.build_release_archive in tests/tools
    from scripts.release_manifest import MANIFEST_NAME, verify_manifest


def build_archive(root: Path, output: Path, prefix: str) -> str:
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verification = verify_manifest(root, manifest)
    if not verification.passed:
        raise ValueError("release manifest is not exact: " + ", ".join(verification.failures[:10]))

    entries = list(manifest["files"])
    members = [(MANIFEST_NAME, manifest_path), *[(item["path"], root / item["path"]) for item in entries]]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, source in members:
            info = zipfile.ZipInfo(f"{prefix}/{relative}", (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if source.stat().st_mode & 0o111 else 0o644) << 16
            archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        expected_names = {f"{prefix}/{MANIFEST_NAME}", *(f"{prefix}/{item['path']}" for item in entries)}
        if len(names) != len(set(names)) or set(names) != expected_names:
            raise ValueError("release archive inventory is not exact")
        for item in entries:
            data = archive.read(f"{prefix}/{item['path']}")
            if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError(f"release archive hash mismatch: {item['path']}")
        if archive.read(f"{prefix}/{MANIFEST_NAME}") != manifest_path.read_bytes():
            raise ValueError("release archive manifest differs from source manifest")
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    digest = build_archive(args.release_root.resolve(), args.output.resolve(), args.prefix)
    print(args.output.resolve())
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
