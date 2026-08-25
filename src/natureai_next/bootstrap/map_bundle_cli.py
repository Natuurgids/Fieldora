"""Verify and install offline Fieldora map bundles without executing bundle content."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from natureai_next.bootstrap.model_bundle_cli import (
    ModelBundleError,
    _bounded_text,
    _file_sha256,
    _malware_scan_attestation,
    _require_token,
    _safe_relative_path,
    _verify_manifest_signature,
)

_PRIMARY_MAP_EXTENSIONS = {".mbtiles", ".pmtiles", ".gpkg", ".pbf"}
_SUPPORT_EXTENSIONS = {
    ".geojson",
    ".json",
    ".style",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
}
_FORBIDDEN_EXTENSIONS = {
    ".py", ".pyc", ".pyo", ".pkl", ".pickle", ".pt", ".pth", ".bin",
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".ps1", ".sh",
}
_DEFAULT_MAX_BYTES = 256 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_MANIFEST_FILES = 50_000
_INSTALL_RECEIPT_NAME = "FIELDORA-INSTALL.json"


class MapBundleError(ModelBundleError):
    """Raised when an offline map bundle violates the trusted import contract."""


@dataclass(frozen=True, slots=True)
class VerifiedMapBundle:
    map_id: str
    version: str
    source: str
    license_id: str
    files: tuple[dict[str, object], ...]
    total_bytes: int
    signature_verified: bool = False
    signing_key_id: str = ""
    malware_scan: dict[str, object] | None = None

    @property
    def artifact_storage_id(self) -> str:
        return f"map:{self.map_id}:{self.version}"

    @property
    def registry_id(self) -> str:
        return f"{self.map_id}@{self.version}"

    def registry_record(self) -> dict[str, object]:
        formats = sorted(
            {
                PurePosixPath(str(entry["path"])).suffix.lower().removeprefix(".")
                for entry in self.files
                if PurePosixPath(str(entry["path"])).suffix.lower()
                in _PRIMARY_MAP_EXTENSIONS
            }
        )
        record: dict[str, object] = {
            "id": self.registry_id,
            "map_id": self.map_id,
            "name": self.map_id,
            "version": self.version,
            "project_id": "platform",
            "network": "offline",
            "status": "installed",
            "artifact_storage_id": self.artifact_storage_id,
            "artifact_total_bytes": self.total_bytes,
            "artifact_files": list(self.files),
            "source": self.source,
            "license_id": self.license_id,
            "verification": "sha256-per-file",
            "manifest_signature": "ed25519" if self.signature_verified else "unsigned",
            "signing_key_id": self.signing_key_id,
            "formats": formats,
        }
        if self.malware_scan is not None:
            record["malware_scan"] = dict(self.malware_scan)
        return record


def verify_map_bundle(
    bundle_dir: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
    trusted_signing_key: Path | None = None,
    require_signature: bool = False,
    require_clean_scan: bool = False,
) -> VerifiedMapBundle:
    if max_total_bytes <= 0:
        raise MapBundleError("maximum bundle size must be positive")
    if bundle_dir.is_symlink():
        raise MapBundleError("bundle root must not be a symlink")
    bundle_dir = bundle_dir.resolve()
    if not bundle_dir.is_dir():
        raise MapBundleError("bundle root must be a directory")
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise MapBundleError("bundle must contain a regular manifest.json")
    try:
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise MapBundleError("manifest.json exceeds the configured size limit")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except MapBundleError:
        raise
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MapBundleError("manifest.json is unreadable or invalid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("package_class") != "map":
        raise MapBundleError("manifest package_class must be map")
    try:
        signature_verified, signing_key_id = _verify_manifest_signature(
            bundle_dir,
            manifest_bytes,
            trusted_signing_key,
            require_signature or require_clean_scan,
        )
    except ModelBundleError as exc:
        raise MapBundleError(str(exc)) from exc

    map_id = _require_token(manifest.get("map_id"), "map_id")
    version = _require_token(manifest.get("version"), "version")
    source = _bounded_text(manifest.get("source"), "source", "offline-bundle")
    license_id = _bounded_text(manifest.get("license_id"), "license_id", "unspecified")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise MapBundleError("manifest files must be a non-empty list")
    if len(entries) > _MAX_MANIFEST_FILES:
        raise MapBundleError("manifest contains too many files")

    verified: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    primary_artifacts = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise MapBundleError("manifest file entries must be objects")
        try:
            relative = _safe_relative_path(entry.get("path"))
        except ModelBundleError as exc:
            raise MapBundleError(str(exc)) from exc
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise MapBundleError(f"duplicate bundle path: {relative_text}")
        seen.add(relative_text)
        suffix = relative.suffix.lower()
        if suffix in _FORBIDDEN_EXTENSIONS or suffix not in _PRIMARY_MAP_EXTENSIONS | _SUPPORT_EXTENSIONS:
            raise MapBundleError(f"unsupported or executable map bundle file: {relative_text}")
        if suffix in _PRIMARY_MAP_EXTENSIONS:
            primary_artifacts += 1
        expected_hash = str(entry.get("sha256") or "").lower()
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise MapBundleError(f"invalid SHA-256 for {relative_text}")
        try:
            expected_size = int(entry.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise MapBundleError(f"invalid size_bytes for {relative_text}") from exc
        if expected_size < 0:
            raise MapBundleError(f"invalid size_bytes for {relative_text}")
        source_path = bundle_dir.joinpath(*relative.parts)
        if source_path.is_symlink() or not source_path.is_file():
            raise MapBundleError(f"bundle file must be a regular non-symlink: {relative_text}")
        try:
            source_path.resolve(strict=True).relative_to(bundle_dir)
        except (OSError, ValueError) as exc:
            raise MapBundleError(f"bundle file escapes bundle root: {relative_text}") from exc
        actual_size = source_path.stat().st_size
        if actual_size != expected_size:
            raise MapBundleError(f"size mismatch for {relative_text}")
        total += actual_size
        if total > max_total_bytes:
            raise MapBundleError("map bundle exceeds configured maximum total size")
        actual_hash = _file_sha256(source_path)
        if actual_hash != expected_hash:
            raise MapBundleError(f"SHA-256 mismatch for {relative_text}")
        verified.append({"path": relative_text, "sha256": actual_hash, "size_bytes": actual_size})
    if primary_artifacts == 0:
        raise MapBundleError("bundle contains no supported primary map artifact")
    verified_files = tuple(verified)
    try:
        malware_scan = _malware_scan_attestation(
            manifest,
            verified_files,
            signature_verified=signature_verified,
            require_clean_scan=require_clean_scan,
        )
    except ModelBundleError as exc:
        raise MapBundleError(str(exc)) from exc
    return VerifiedMapBundle(
        map_id, version, source, license_id, verified_files, total,
        signature_verified, signing_key_id, malware_scan,
    )


def install_map_bundle(
    bundle_dir: Path,
    map_store: Path,
    **kwargs: object,
) -> tuple[VerifiedMapBundle, Path]:
    verified = verify_map_bundle(bundle_dir, **kwargs)
    map_store.mkdir(parents=True, exist_ok=True)
    destination = map_store / verified.map_id / verified.version
    if destination.exists():
        raise MapBundleError(f"map bundle is already installed: {verified.registry_id}")
    staging_root = Path(tempfile.mkdtemp(prefix=".fieldora-map-", dir=map_store))
    try:
        staging = staging_root / verified.map_id / verified.version
        staging.mkdir(parents=True)
        for entry in verified.files:
            relative = PurePosixPath(str(entry["path"]))
            source_path = bundle_dir.resolve().joinpath(*relative.parts)
            target_path = staging.joinpath(*relative.parts)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path, follow_symlinks=False)
        shutil.copyfile(bundle_dir.resolve() / "manifest.json", staging / "manifest.json", follow_symlinks=False)
        signature_path = bundle_dir.resolve() / "manifest.sig"
        if signature_path.is_file() and not signature_path.is_symlink():
            shutil.copyfile(signature_path, staging / "manifest.sig", follow_symlinks=False)
        receipt = json.dumps(verified.registry_record(), sort_keys=True, indent=2) + "\n"
        (staging / _INSTALL_RECEIPT_NAME).write_text(receipt, encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    shutil.rmtree(staging_root, ignore_errors=True)
    return verified, destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or install an offline Fieldora map bundle")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--map-store", type=Path)
    parser.add_argument("--max-total-bytes", type=int, default=_DEFAULT_MAX_BYTES)
    parser.add_argument("--trusted-signing-key", type=Path)
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--require-clean-scan", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    kwargs = {
        "max_total_bytes": args.max_total_bytes,
        "trusted_signing_key": args.trusted_signing_key,
        "require_signature": args.require_signature,
        "require_clean_scan": args.require_clean_scan,
    }
    try:
        if args.map_store is None:
            verified = verify_map_bundle(args.bundle, **kwargs)
            destination = None
        else:
            verified, destination = install_map_bundle(args.bundle, args.map_store, **kwargs)
    except MapBundleError as exc:
        print(str(exc))
        return 2
    payload = verified.registry_record()
    if destination is not None:
        payload["installed_path"] = str(destination)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
