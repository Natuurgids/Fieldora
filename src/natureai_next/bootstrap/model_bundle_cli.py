"""Verify and install offline Fieldora model bundles without executing bundle code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_MODEL_EXTENSIONS = {".safetensors", ".onnx", ".gguf"}
_SUPPORT_EXTENSIONS = {
    ".json",
    ".txt",
    ".md",
    ".model",
    ".vocab",
    ".merges",
    ".yaml",
    ".yml",
}
_FORBIDDEN_EXTENSIONS = {
    ".py",
    ".pyc",
    ".pyo",
    ".pkl",
    ".pickle",
    ".pt",
    ".pth",
    ".bin",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
}
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024 * 1024


class ModelBundleError(ValueError):
    """Raised when an offline model bundle violates the trusted import contract."""


@dataclass(frozen=True, slots=True)
class VerifiedModelBundle:
    model_id: str
    version: str
    source: str
    license_id: str
    files: tuple[dict[str, object], ...]
    total_bytes: int

    def registry_record(self, install_path: Path) -> dict[str, object]:
        return {
            "id": self.model_id,
            "name": self.model_id,
            "version": self.version,
            "provider_id": "fieldora-offline",
            "network": "offline",
            "enabled": True,
            "status": "installed",
            "artifact_store_path": str(install_path),
            "artifact_total_bytes": self.total_bytes,
            "artifact_files": list(self.files),
            "source": self.source,
            "license_id": self.license_id,
            "verification": "sha256-per-file",
        }


def _require_token(value: object, field: str) -> str:
    token = str(value or "").strip()
    if not token or token in {".", ".."} or "/" in token or "\\" in token:
        raise ModelBundleError(f"manifest {field} must be a non-empty path-safe token")
    return token


def _safe_relative_path(value: object) -> PurePosixPath:
    raw = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ModelBundleError(f"unsafe bundle path: {raw!r}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_bundle(
    bundle_dir: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
) -> VerifiedModelBundle:
    bundle_dir = bundle_dir.resolve()
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ModelBundleError("bundle must contain a regular manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelBundleError("manifest.json is unreadable or invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ModelBundleError("manifest.json must contain an object")

    model_id = _require_token(manifest.get("model_id"), "model_id")
    version = _require_token(manifest.get("version"), "version")
    source = str(manifest.get("source") or "offline-bundle").strip()
    license_id = str(manifest.get("license_id") or "unspecified").strip()
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ModelBundleError("manifest files must be a non-empty list")

    verified: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    model_artifacts = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ModelBundleError("manifest file entries must be objects")
        relative = _safe_relative_path(entry.get("path"))
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise ModelBundleError(f"duplicate bundle path: {relative_text}")
        seen.add(relative_text)
        suffix = relative.suffix.lower()
        if suffix in _FORBIDDEN_EXTENSIONS or suffix not in _MODEL_EXTENSIONS | _SUPPORT_EXTENSIONS:
            raise ModelBundleError(f"unsupported or executable model bundle file: {relative_text}")
        if suffix in _MODEL_EXTENSIONS:
            model_artifacts += 1

        expected_hash = str(entry.get("sha256") or "").lower()
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise ModelBundleError(f"invalid SHA-256 for {relative_text}")
        try:
            expected_size = int(entry.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ModelBundleError(f"invalid size_bytes for {relative_text}") from exc
        if expected_size < 0:
            raise ModelBundleError(f"invalid size_bytes for {relative_text}")

        source_path = bundle_dir.joinpath(*relative.parts)
        if source_path.is_symlink() or not source_path.is_file():
            raise ModelBundleError(f"bundle file must be a regular non-symlink: {relative_text}")
        try:
            resolved = source_path.resolve(strict=True)
            resolved.relative_to(bundle_dir)
        except (OSError, ValueError) as exc:
            raise ModelBundleError(f"bundle file escapes bundle root: {relative_text}") from exc
        actual_size = source_path.stat().st_size
        if actual_size != expected_size:
            raise ModelBundleError(f"size mismatch for {relative_text}")
        total += actual_size
        if total > max_total_bytes:
            raise ModelBundleError("model bundle exceeds configured maximum total size")
        actual_hash = _file_sha256(source_path)
        if actual_hash != expected_hash:
            raise ModelBundleError(f"SHA-256 mismatch for {relative_text}")
        verified.append(
            {"path": relative_text, "sha256": actual_hash, "size_bytes": actual_size}
        )

    if model_artifacts == 0:
        raise ModelBundleError("bundle contains no supported model artifact")
    return VerifiedModelBundle(
        model_id=model_id,
        version=version,
        source=source,
        license_id=license_id,
        files=tuple(verified),
        total_bytes=total,
    )


def install_model_bundle(
    bundle_dir: Path,
    model_store: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
) -> tuple[VerifiedModelBundle, Path]:
    verified = verify_model_bundle(bundle_dir, max_total_bytes=max_total_bytes)
    model_store.mkdir(parents=True, exist_ok=True)
    destination = model_store / verified.model_id / verified.version
    if destination.exists():
        raise ModelBundleError(f"model version is already installed: {destination}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".fieldora-model-", dir=parent))
    try:
        for entry in verified.files:
            relative = PurePosixPath(str(entry["path"]))
            source = bundle_dir.resolve().joinpath(*relative.parts)
            target = temp_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
        receipt = verified.registry_record(destination)
        (temp_root / "FIELDORA-INSTALL.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_root, destination)
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return verified, destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldora-model-bundle",
        description="Verify or install an offline Fieldora model bundle.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "install"):
        command = sub.add_parser(name)
        command.add_argument("bundle", type=Path)
        command.add_argument("--max-bytes", type=int, default=_DEFAULT_MAX_BYTES)
        if name == "install":
            command.add_argument("--store", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            verified = verify_model_bundle(args.bundle, max_total_bytes=args.max_bytes)
            output = {
                "model_id": verified.model_id,
                "version": verified.version,
                "total_bytes": verified.total_bytes,
                "verification": "sha256-per-file",
            }
        else:
            verified, destination = install_model_bundle(
                args.bundle,
                args.store,
                max_total_bytes=args.max_bytes,
            )
            output = verified.registry_record(destination)
    except ModelBundleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps({"ok": True, **output}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
