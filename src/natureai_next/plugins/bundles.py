"""Offline-first extension bundle verification and installation."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.source_lifecycle import (
    SourceRecord,
    SourceRegistryService,
    SourceState,
)
from natureai_next.plugin_api import PluginKind, PluginManifest
from natureai_next.plugins.manifest import parse_manifest, validate_compatibility


@dataclass(frozen=True, slots=True)
class InstalledBundle:
    manifest: PluginManifest
    install_path: Path
    verified_files: tuple[str, ...]


class OfflineBundleRemover:
    """Remove installed bundle material independently from Aperture knowledge."""

    def __init__(self, install_root: Path, source_registry: SourceRegistryService) -> None:
        self._root = install_root
        self._registry = source_registry

    def remove(
        self,
        source_id: str,
        options=None,
        *,
        remove_runtime_files: bool = True,
        remove_all_versions: bool = True,
    ) -> tuple[Path, ...]:
        from natureai_next.application.source_lifecycle import SourceRemovalOptions

        policy = options or SourceRemovalOptions(remove_runtime_files=remove_runtime_files)
        removed: list[Path] = []
        source_root = self._root / source_id
        if policy.remove_runtime_files and source_root.exists():
            if remove_all_versions:
                shutil.rmtree(source_root)
                removed.append(source_root)
            else:
                record = self._registry.get(source_id)
                version_path = source_root / record.version
                if version_path.exists():
                    shutil.rmtree(version_path)
                    removed.append(version_path)
        self._registry.remove(source_id, policy)
        return tuple(removed)


class OfflineBundleInstaller:
    def __init__(
        self,
        install_root: Path,
        source_registry: SourceRegistryService,
        *,
        api_version: str,
        application_version: str,
    ) -> None:
        self._root = install_root
        self._registry = source_registry
        self._api_version = api_version
        self._application_version = application_version

    def install(self, bundle: Path) -> InstalledBundle:
        self._root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="aperture-bundle-") as temporary:
            staging = Path(temporary)
            if bundle.is_dir():
                shutil.copytree(bundle, staging / "bundle", dirs_exist_ok=True)
            elif zipfile.is_zipfile(bundle):
                self._extract_safe(bundle, staging / "bundle")
            else:
                raise ValueError("bundle must be a directory or ZIP archive")
            root = staging / "bundle"
            document = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest = parse_manifest(document)
            if manifest.kind not in {PluginKind.CAPABILITY, PluginKind.SOURCE}:
                raise ValueError("offline bundle kind must be capability or source")
            validate_compatibility(
                manifest,
                api_version=self._api_version,
                application_version=self._application_version,
            )
            verified = self._verify_files(root, manifest.checksums)
            destination = self._root / manifest.plugin_id / manifest.version
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, destination)
            self._registry.register(
                SourceRecord(
                    source_id=manifest.plugin_id,
                    kind=manifest.kind.value,
                    display_name=manifest.display_name,
                    version=manifest.version,
                    state=SourceState.INSTALLED
                    if manifest.offline
                    else SourceState.REQUIRES_DOWNLOAD,
                    licence=manifest.license,
                    attribution=manifest.attribution,
                    checksum=_tree_checksum(destination, verified),
                )
            )
            return InstalledBundle(manifest, destination, verified)

    @staticmethod
    def _extract_safe(archive: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()
        with zipfile.ZipFile(archive) as handle:
            for member in handle.infolist():
                target = (destination / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise ValueError("bundle contains an unsafe path")
            handle.extractall(destination)

    @staticmethod
    def _verify_files(root: Path, checksums: Mapping[str, str]) -> tuple[str, ...]:
        verified: list[str] = []
        for relative, expected in sorted(checksums.items()):
            path = (root / relative).resolve()
            if root.resolve() not in path.parents or not path.is_file():
                raise ValueError(f"bundle file is missing or unsafe: {relative}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.casefold() != expected.casefold():
                raise ValueError(f"checksum mismatch for {relative}")
            verified.append(relative)
        return tuple(verified)


def _tree_checksum(root: Path, files: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8"))
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()
