"""Platform path resolution for installed and test environments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

_APP_NAME = "Fieldora V5"
_APP_AUTHOR = "Fieldora"


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    local_root: Path
    roaming_root: Path
    config_file: Path
    preferences_file: Path
    state_dir: Path
    cache_dir: Path
    logs_dir: Path
    models_dir: Path
    taxonomy_packages_dir: Path
    updates_dir: Path
    plugins_dir: Path
    subsystem_databases_dir: Path
    offline_map_packages_dir: Path

    def ensure_directories(self) -> None:
        for path in (
            self.local_root,
            self.roaming_root,
            self.state_dir,
            self.cache_dir,
            self.logs_dir,
            self.models_dir,
            self.taxonomy_packages_dir,
            self.updates_dir,
            self.plugins_dir,
            self.subsystem_databases_dir,
            self.offline_map_packages_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_application_paths(config_root: Path | None = None) -> ApplicationPaths:
    if config_root is None:
        configured = os.environ.get("APERTURE_DATA_ROOT") or os.environ.get("NATUREAI_DATA_ROOT")
        if configured:
            config_root = Path(configured)
    if config_root is not None:
        local_root = config_root.expanduser().resolve()
        roaming_root = local_root / "roaming"
    else:
        dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR, roaming=False)
        roaming_dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR, roaming=True)
        local_root = Path(dirs.user_data_dir)
        roaming_root = Path(roaming_dirs.user_config_dir)

    return ApplicationPaths(
        local_root=local_root,
        roaming_root=roaming_root,
        config_file=local_root / "app-config.toml",
        preferences_file=roaming_root / "user-preferences.toml",
        state_dir=local_root / "state",
        cache_dir=local_root / "cache",
        logs_dir=local_root / "logs",
        models_dir=local_root / "models",
        taxonomy_packages_dir=local_root / "taxonomy-packages",
        updates_dir=local_root / "updates",
        plugins_dir=local_root / "plugins",
        subsystem_databases_dir=local_root / "subsystems",
        offline_map_packages_dir=local_root / "offline-maps",
    )
