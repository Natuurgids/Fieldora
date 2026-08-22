"""Bootstrap-only preparation for optional vector-map presentation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class MapWebProfileBundle:
    profile: Any
    handler: Any


def prepare_map_archive_scheme(register: Callable[[], None] | None = None) -> bool:
    """Register the private scheme without making WebEngine a startup dependency."""
    try:
        if register is None:
            from natureai_next.ui.qt.map_archive_scheme import register_aperture_map_scheme

            register = register_aperture_map_scheme
        register()
    except (ImportError, OSError, RuntimeError) as exc:
        logging.getLogger("natureai_next.bootstrap").info(
            "Optional vector map scheme unavailable",
            extra={"context": {"error_type": type(exc).__name__, "detail": str(exc)}},
        )
        return False
    return True


def create_map_web_profile(map_factory: Any, parent: Any = None) -> MapWebProfileBundle:
    """Compose one off-the-record, map-only WebEngine profile lazily."""
    from PySide6.QtWebEngineCore import QWebEngineProfile

    from natureai_next.infrastructure.subsystems.map_archive import CatalogVectorTileReader
    from natureai_next.infrastructure.subsystems.maps import OfflineMapCatalog
    from natureai_next.ui.qt.map_archive_scheme import (
        create_map_archive_scheme_handler,
        install_map_archive_scheme_handler,
    )

    profile = QWebEngineProfile(parent)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    reader = CatalogVectorTileReader(OfflineMapCatalog(map_factory))
    handler = create_map_archive_scheme_handler(reader, profile)
    install_map_archive_scheme_handler(profile, handler)
    return MapWebProfileBundle(profile, handler)
