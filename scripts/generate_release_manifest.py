"""Generate the deterministic release manifest for an Aperture package tree."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from release_manifest import write_manifest


def _read_version(root: Path) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def _default_build(root: Path) -> str:
    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    match = re.search(r"\bBuild\s+(\d+)\b", notes, flags=re.IGNORECASE)
    if not match:
        raise ValueError("RELEASE_NOTES.md does not contain a build number")
    return f"build{match.group(1)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version")
    parser.add_argument("--build")
    args = parser.parse_args()
    root = args.release_root.resolve()
    path = write_manifest(
        root,
        version=args.version or _read_version(root),
        build=args.build or _default_build(root),
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
