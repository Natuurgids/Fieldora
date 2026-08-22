"""TOML-backed configuration source with atomic persistence and backups."""

from __future__ import annotations

import shutil
import tomllib
from collections.abc import Mapping
from pathlib import Path

from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes
from natureai_next.infrastructure.filesystem.toml_codec import dumps_toml
from natureai_next.shared.errors import ConfigurationError, ErrorCode, ErrorDescriptor


class TomlConfigurationStore:
    def read(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            with path.open("rb") as stream:
                return dict(tomllib.load(stream))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(
                ErrorDescriptor(
                    code=ErrorCode.CONFIG_READ_FAILED,
                    summary=f"Could not read configuration file {path.name}.",
                    technical_detail=str(exc),
                    remediation="Correct the file or restore its most recent backup.",
                )
            ) from exc

    def write(self, path: Path, document: Mapping[str, object]) -> None:
        encoded = dumps_toml(document).encode("utf-8")
        try:
            tomllib.loads(encoded.decode("utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                ErrorDescriptor(
                    code=ErrorCode.CONFIG_WRITE_FAILED,
                    summary="Generated configuration was invalid.",
                    technical_detail=str(exc),
                )
            ) from exc
        try:
            atomic_write_bytes(path, encoded)
        except OSError as exc:
            raise ConfigurationError(
                ErrorDescriptor(
                    code=ErrorCode.CONFIG_WRITE_FAILED,
                    summary=f"Could not write configuration file {path.name}.",
                    technical_detail=str(exc),
                    remediation="Check that the configuration directory is writable.",
                )
            ) from exc

    def backup(self, path: Path, suffix: str) -> Path | None:
        if not path.exists():
            return None
        backup_path = path.with_name(f"{path.name}.{suffix}.bak")
        try:
            shutil.copy2(path, backup_path)
        except OSError as exc:
            raise ConfigurationError(
                ErrorDescriptor(
                    code=ErrorCode.CONFIG_MIGRATION_FAILED,
                    summary=f"Could not back up configuration file {path.name}.",
                    technical_detail=str(exc),
                )
            ) from exc
        return backup_path
