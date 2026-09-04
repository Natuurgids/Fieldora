"""Top-level offline-first API composition for the managed Fieldora server."""

from __future__ import annotations

import os
from collections.abc import Callable

from natureai_next.server.administration_actions_api import AdministrationActionsApiMixin
from natureai_next.server.bounded_upload_web import BoundedUploadWebApiMixin
from natureai_next.server.capacity_availability_module_web import (
    CapacityAvailabilityModuleWebApiMixin,
)
from natureai_next.server.capacity_module_web import CapacityModuleWebApiMixin
from natureai_next.server.dossier_module_web import DossierModuleWebApiMixin
from natureai_next.server.facility_actions_api import FacilityActionsApiMixin
from natureai_next.server.filtering import FilteringApiMixin
from natureai_next.server.knowledge_parity_api import KnowledgeParityApiMixin
from natureai_next.server.library_collections_api import LibraryCollectionsApiMixin
from natureai_next.server.linked_storage_api import LinkedStorageApiMixin, LinkedStorageRepository
from natureai_next.server.linked_storage_browser_api import LinkedStorageBrowserFieldoraApi
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.linked_storage_sources_api import LinkedStorageSourcesApiMixin
from natureai_next.server.modular_shell_web import ModularShellWebApiMixin
from natureai_next.server.observation_actions_api import ObservationActionsApiMixin
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.offline_map_store_api import InstalledMapApiMixin
from natureai_next.server.offline_model_store_api import InstalledModelApiMixin
from natureai_next.server.offline_sync_api import OfflineSyncApiMixin, OfflineSyncRepository
from natureai_next.server.optimistic_concurrency_web import OptimisticConcurrencyWebApiMixin
from natureai_next.server.original_derivative_api import OriginalDerivativeApiMixin
from natureai_next.server.pagination_api import PaginationApiMixin
from natureai_next.server.portfolio_module_web import PortfolioModuleWebApiMixin
from natureai_next.server.postgres_project_task_schema import ensure_managed_project_task_schema
from natureai_next.server.postgres_web_indexes import ensure_managed_web_postgres_indexes
from natureai_next.server.project_capacity_integration_web import (
    ProjectCapacityIntegrationWebApiMixin,
)
from natureai_next.server.project_core_module_web import ProjectCoreModuleWebApiMixin
from natureai_next.server.project_creation_module_web import ProjectCreationModuleWebApiMixin
from natureai_next.server.project_evidence_actions_module_web import (
    ProjectEvidenceActionsModuleWebApiMixin,
)
from natureai_next.server.project_hierarchy_web import ProjectHierarchyWebApiMixin
from natureai_next.server.project_idempotency import (
    ProjectIdempotencyApiMixin,
    wrap_project_management,
)
from natureai_next.server.project_idempotency_web import ProjectIdempotencyWebApiMixin
from natureai_next.server.project_lifecycle_module_web import ProjectLifecycleModuleWebApiMixin
from natureai_next.server.project_lifecycle_web import ProjectLifecycleWebApiMixin
from natureai_next.server.project_progress_module_web import ProjectProgressModuleWebApiMixin
from natureai_next.server.project_research_integration_web import (
    ProjectResearchIntegrationWebApiMixin,
)
from natureai_next.server.project_runtime_web import ProjectRuntimeWebApiMixin
from natureai_next.server.project_task_edit_module_web import ProjectTaskEditModuleWebApiMixin
from natureai_next.server.project_task_editing import wrap_project_task_editing
from natureai_next.server.project_work_actions_module_web import ProjectWorkActionsModuleWebApiMixin
from natureai_next.server.research_records_api import ResearchRecordsApiMixin
from natureai_next.server.structured_errors import StructuredErrorApiMixin
from natureai_next.server.visible_control_audit_api import VisibleControlAuditApiMixin


class OfflineFirstFieldoraApi(
    ModularShellWebApiMixin,
    BoundedUploadWebApiMixin,
    ProjectResearchIntegrationWebApiMixin,
    ProjectCapacityIntegrationWebApiMixin,
    DossierModuleWebApiMixin,
    CapacityAvailabilityModuleWebApiMixin,
    CapacityModuleWebApiMixin,
    ProjectTaskEditModuleWebApiMixin,
    ProjectProgressModuleWebApiMixin,
    ProjectCreationModuleWebApiMixin,
    ProjectLifecycleModuleWebApiMixin,
    ProjectEvidenceActionsModuleWebApiMixin,
    ProjectWorkActionsModuleWebApiMixin,
    ProjectCoreModuleWebApiMixin,
    PortfolioModuleWebApiMixin,
    ProjectLifecycleWebApiMixin,
    ProjectHierarchyWebApiMixin,
    ProjectRuntimeWebApiMixin,
    OptimisticConcurrencyWebApiMixin,
    StructuredErrorApiMixin,
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
    def configure_offline_sync(cls, factory: Callable[[], OfflineSyncRepository] | None) -> None:
        cls._offline_sync_factory = factory

    @classmethod
    def configure_linked_storage(cls, factory: Callable[[], LinkedStorageRepository] | None) -> None:
        cls._linked_storage_factory = factory

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        project_management = getattr(self, "_project_management", None)
        ensure_managed_web_postgres_indexes(
            project_management=project_management,
            media=getattr(self, "_media", None),
            science=getattr(self, "_science", None),
        )
        ensure_managed_project_task_schema(project_management)
        self._project_management = wrap_project_task_editing(
            wrap_project_management(project_management)
        )
        sync_factory = type(self)._offline_sync_factory
        linked_factory = type(self)._linked_storage_factory
        self._offline_sync = None if sync_factory is None else sync_factory()
        self._linked_storage = None if linked_factory is None else linked_factory()
        enabled = os.environ.get("FIELDORA_STORAGE_SERVICE_ENABLED", "").strip().casefold()
        listener_enabled = enabled in {"1", "true", "yes", "on"}
        self._runtime_profile["storage_service_listener"] = "listening" if listener_enabled else "disabled"
        self._runtime_profile["storage_service_mtls"] = "required"
        if listener_enabled:
            self._runtime_profile["storage_service_port"] = os.environ.get("FIELDORA_STORAGE_SERVICE_PORT", "8766").strip()
