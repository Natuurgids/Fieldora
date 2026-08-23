"""Top-level offline-first API composition for the managed Fieldora server."""

from __future__ import annotations

from collections.abc import Callable

from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.offline_sync_api import OfflineSyncApiMixin, OfflineSyncRepository


class OfflineFirstFieldoraApi(OfflineSyncApiMixin, BrowserFunctionalityFieldoraApi):
    """Browser/platform API with an explicitly configured synchronization repository."""

    _offline_sync_factory: Callable[[], OfflineSyncRepository] | None = None

    @classmethod
    def configure_offline_sync(
        cls, factory: Callable[[], OfflineSyncRepository] | None
    ) -> None:
        cls._offline_sync_factory = factory

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        factory = type(self)._offline_sync_factory
        self._offline_sync = None if factory is None else factory()
