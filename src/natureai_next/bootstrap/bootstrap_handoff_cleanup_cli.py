"""Expire temporary installer handoff credentials without platform-specific schedulers."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

_DEFAULT_DIRECTORY = Path("/run/fieldora-bootstrap-handoff")
_DEFAULT_CREDENTIALS = "ADMIN-CREDENTIALS.txt"
_DEFAULT_EXPIRY = "EXPIRES-AT-EPOCH"


def _safe_child(directory: Path, name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("handoff file names must be simple basenames")
    root = directory.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise ValueError("handoff file must remain inside the handoff directory")
    return candidate


def expire_handoff(
    directory: Path,
    *,
    now_epoch: int | None = None,
    credentials_name: str = _DEFAULT_CREDENTIALS,
    expiry_name: str = _DEFAULT_EXPIRY,
) -> bool:
    """Delete only expired plaintext handoff material; never touch account state."""
    credentials = _safe_child(directory, credentials_name)
    expiry = _safe_child(directory, expiry_name)
    if not expiry.is_file():
        return False
    try:
        expires_at = int(expiry.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    if expires_at < 1:
        return False
    now = int(time.time()) if now_epoch is None else int(now_epoch)
    if now < expires_at:
        return False
    credentials.unlink(missing_ok=True)
    expiry.unlink(missing_ok=True)
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete expired Fieldora bootstrap handoff credentials.",
    )
    parser.add_argument("--directory", type=Path, default=_DEFAULT_DIRECTORY)
    parser.add_argument("--credentials-name", default=_DEFAULT_CREDENTIALS)
    parser.add_argument("--expiry-name", default=_DEFAULT_EXPIRY)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.interval_seconds < 60:
        raise SystemExit("--interval-seconds must be at least 60")
    while True:
        expired = expire_handoff(
            args.directory,
            credentials_name=args.credentials_name,
            expiry_name=args.expiry_name,
        )
        if expired:
            print("Fieldora bootstrap credential handoff expired and was removed.")
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
