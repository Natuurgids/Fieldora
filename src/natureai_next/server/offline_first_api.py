"""Top-level offline-first API composition for the managed Fieldora server."""

from __future__ import annotations

import os
from collections.abc import Callable

from natureai_next.server.administration_actions_api import AdministrationActionsApiMixin
from natureai_next.server.facility_actions_api import FacilityActionsApiMixin
from natureai_next.server.filtering import FilteringApiMixin
from natureai_next.server.knowledge_parity_api import KnowledgeParityApiMixin
from natureai_next.server.library_collections_api import LibraryCollectionsApiMixin
from natureai_next.server.linked_storage_api import (
    LinkedStorageApiMixin,
    LinkedStorageRepository,
)
from natureai_next.server.linked_storage_browser_api import LinkedStorageBrowserFieldoraApi
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.linked_storage_sources_api import LinkedStorageSourcesApiMixin
from natureai_next.server.observation_actions_api import ObservationActionsApiMixin
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.offline_map_store_api import InstalledMapApiMixin
from natureai_next.server.offline_model_store_api import InstalledModelApiMixin
from natureai_next.server.offline_sync_api import OfflineSyncApiMixin, OfflineSyncRepository
from natureai_next.server.optimistic_concurrency_web import OptimisticConcurrencyWebApiMixin
from natureai_next.server.original_derivative_api import OriginalDerivativeApiMixin
from natureai_next.server.pagination_api import PaginationApiMixin
from natureai_next.server.project_idempotency import (
    ProjectIdempotencyApiMixin,
    wrap_project_management,
)
from natureai_next.server.project_idempotency_web import ProjectIdempotencyWebApiMixin
from natureai_next.server.research_records_api import ResearchRecordsApiMixin
from natureai_next.server.visible_control_audit_api import VisibleControlAuditApiMixin


class OfflineFirstFieldoraApi(
    OptimisticConcurrencyWebApiMixin,
    ProjectIdempotencyWebApiMixin,
    ProjectIdempotencyApiMixin,
    FilteringApiMixin,
    PaginationApiMixin,
    VisibleControlAuditApiMixin,
    ObservationActionsApiMixin,
    AdministrationActionsApiMixin,
    FacilityActionsApiMixin,
    ResearchRecordsApiMixin,
    OriginalDerivativeApiMixin,
    LibraryCollectionsApiMixin,
    KnowledgeParityApiMixin,
    ObservationParityApiMixin,
    InstalledMapApiMixin,
    InstalledModelApiMixin,
    LinkedStorageOperatorApiMixin,
    LinkedStorageSourcesApiMixin,
    LinkedStorageApiMixin,
    OfflineSyncApiMixin,
    LinkedStorageBrowserFieldoraApi,
):
    """Browser/platform API with explicitly configured offline-first repositories."""

    _offline_sync_factory: Callable[[], OfflineSyncRepository] | None = None
    _linked_storage_factory: Callable[[], LinkedStorageRepository] | None = None

    @classmethod
    def configure_offline_sync(
        cls, factory: Callable[[], OfflineSyncRepository] | None
    ) -> None:
        cls._offline_sync_factory = factory

    @classmethod
    def configure_linked_storage(
        cls, factory: Callable[[], LinkedStorageRepository] | None
    ) -> None:
        cls._linked_storage_factory = factory

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._project_management = wrap_project_management(
            getattr(self, "_project_management", None)
        )
        sync_factory = type(self)._offline_sync_factory
        linked_factory = type(self)._linked_storage_factory
        self._offline_sync = None if sync_factory is None else sync_factory()
        self._linked_storage = None if linked_factory is None else linked_factory()
        enabled = os.environ.get("FIELDORA_STORAGE_SERVICE_ENABLED", "").strip().casefold()
        listener_enabled = enabled in {"1", "true", "yes", "on"}
        self._runtime_profile["storage_service_listener"] = (
            "listening" if listener_enabled else "disabled"
        )
        self._runtime_profile["storage_service_mtls"] = "required"
        if listener_enabled:
            self._runtime_profile["storage_service_port"] = os.environ.get(
                "FIELDORA_STORAGE_SERVICE_PORT", "8766"
            ).strip()
