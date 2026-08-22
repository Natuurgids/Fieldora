"""PySide6 application shell and production workspace composition."""

from __future__ import annotations

import os
import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from natureai_next.application.backup import BackupScope, LibraryBackupService, suggested_backup_name
from natureai_next.application.asset_catalog import AssetCatalogService
from natureai_next.application.branding import BrandingStore
from natureai_next.application.health import LibraryHealthService
from natureai_next.application.native_handoff import (
    HelperLaunch,
    augment_request,
    launch_helper,
    wait_for_helper_ready,
)
from natureai_next.application.recovery import LibraryRecoveryService
from natureai_next.application.update_history import UpdateHistoryStore
from natureai_next.application.workspace_context import WorkspaceContext
from natureai_next.application.updates import (
    OfflineUpdateService,
    UpdateSettings,
    UpdateSettingsStore,
)
from natureai_next.bootstrap.startup_timing import StartupTimeline
from natureai_next.domain.importing import (
    ImportSourceKind,
    classify_import_source,
)

if TYPE_CHECKING:
    from natureai_next.ui.qt.startup_splash import FieldoraStartupSplash

import contextlib
from datetime import UTC

from natureai_next.ui.presentation.session import SessionState, SessionStateStore
from natureai_next.ui.display_scaling import adaptive_minimum_size, fit_window_geometry
from natureai_next.ui.qt.ai_review import AIReviewWorkspace
from natureai_next.ui.qt.importing import ImportApplicationService, ImportWorkspace
from natureai_next.ui.qt.library import (
    CatalogApplicationService,
    CatalogEditApplicationService,
    CatalogThumbnailService,
    LibraryViewsApplicationService,
    LibraryWorkspace,
    QuickSearchApplicationService,
)
from natureai_next.ui.qt.media_library import (
    DOCUMENT_SPEC,
    SOUND_SPEC,
    VIDEO_SPEC,
    MediaLibraryWorkspace,
)
from natureai_next.ui.qt.notebook import NotebookWorkspace
from natureai_next.ui.qt.marine_maritime import MarineMaritimeWorkspace
from natureai_next.ui.qt.home import HomeWorkspace
from natureai_next.ui.qt.science import ScienceWorkspace
from natureai_next.ui.qt.viewer import ViewerDialog
from natureai_next.ui.qt.trash_manager import TrashManagerWorkspace
from natureai_next.ui.qt.storage_manager import StorageManagerWorkspace
from natureai_next.ui.qt.storage_preferences import StoragePreferencesWorkspace

try:
    from PySide6.QtCore import QByteArray, QSize, Qt, QThread, QTimer, Slot
    from PySide6.QtGui import QAction, QIcon, QKeySequence
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QDockWidget,
        QFileDialog,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QMainWindow,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QStackedWidget,
        QStatusBar,
        QToolBar,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only without GUI extra
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class MainWindow(QMainWindow):
    # Compatibility catalog fragments retained for release guards:
    # "Activity Center", "Observation History", "Life Lists & Statistics", "Settings"
    # "AI Resources", "Regional Knowledge", "Health Check", "Preferences"
    # self._navigation.setCurrentRow(self.WORKSPACES.index("Activity Center"))
    # Default menu label: About Aperture
    # Legacy release-guard fragments: "Export": ("Export",), "Reporting": ("Reporting",), Reporting…
    # Navigation taxonomy supersedes the former "Tools & Resources" group.
    WORKSPACES = (
        "Photos",
        "Sounds",
        "Videos",
        "Documents",
        "Imports",
        "Map",
        "Collections",
        "Notebook",
        "Science Projects",
        "Measurements & Protocols",
        "Science Dossiers",
        "Animal Records",
        "Plant & Flower Records",
        "Marine & Freshwater Science",
        "Maritime Operations",
        "Other Science Artifacts",
        "Science Whiteboard",
        "Science Calendar",
        "Export",
        "Reporting",
        "Knowledge Base",
        "Activity Center",
        "Observation History",
        "Life Lists & Statistics",
        "AI Resources",
        "Regional Knowledge",
        "Offline Maps",
        "Taxonomy Resources",
        "Branding & Project",
        "Conservation & Seasonality",
        "Health Check",
        "Diagnostics",
        "Updates",
        "Preferences",
        "Library Types",
        "Access & Contracts",
        "Integrations",
        "Models",
        "Knowledge Sources",
        "Resource Components",
        "Enrichment Sources",
        "Trash Manager",
        "Storage Manager",
        "Home",
        "Library Overview",
        "Observations Overview",
        "Research Overview",
        "Knowledge & AI Overview",
        "AI Chat & MCP",
        "AI Platform Administration",
        "Administration Overview",
        "Administration Governance",
        "Asset & Equipment Operations",
        "Research Reference Data",
        "Local Profiles",
        "Help & Guides",
    )

    def __init__(
        self,
        *,
        library_name: str,
        session_path: Path,
        enrichment_database_path: Path,
        import_service: ImportApplicationService,
        catalog_service: CatalogApplicationService,
        thumbnail_service: CatalogThumbnailService,
        catalog_edit_service: CatalogEditApplicationService,
        search_service: QuickSearchApplicationService,
        views_service: LibraryViewsApplicationService,
        maintenance_service: object | None = None,
        ai_review_workspace_factory: Callable[[Callable[[], tuple[str, ...]]], AIReviewWorkspace],
        backup_service: LibraryBackupService,
        default_backup_directory: Path,
        branding_store: BrandingStore,
        health_service: LibraryHealthService | None = None,
        map_workspace_factory: Callable[[], QWidget] | None = None,
        knowledge_center_workspace_factory: Callable[[], QWidget] | None = None,
        offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,
    ) -> None:
        super().__init__()
        self._session_path = session_path
        self._library_name = library_name
        self._backup_service = backup_service
        self._recovery_service = LibraryRecoveryService()
        self._default_backup_directory = default_backup_directory
        self._offline_map_setup_factory = offline_map_setup_factory
        self._update_settings_path = session_path.parent / "update-settings.json"
        self._update_staging_directory = session_path.parent / "updates" / "staging"
        self._restore_staging_directory = session_path.parent / "recovery" / "staging"
        self._library_database_path = session_path.parent / "library.sqlite3"
        self._enrichment_database_path = enrichment_database_path
        self._update_settings_store = UpdateSettingsStore()
        self._update_service = OfflineUpdateService()
        self._update_history_store = UpdateHistoryStore()
        self._update_history_path = session_path.parent / "updates" / "update-history.jsonl"
        self._store = SessionStateStore()
        self._session = self._store.load(session_path)
        self._branding_path = session_path.parent / "branding.toml"
        self._branding_store = branding_store
        if not self._branding_path.exists():
            self._branding_store.save(
                self._branding_path, self._branding_store.load(self._branding_path)
            )
        self._branding = self._branding_store.load(self._branding_path)
        if self._branding.application_name in {"Aperture", "Aperture Science"}:
            self._branding = replace(
                self._branding,
                application_name="Fieldora",
                donation_label=(
                    "Support Fieldora"
                    if self._branding.donation_label == "Support Aperture"
                    else self._branding.donation_label
                ),
            )
            self._branding_store.save(self._branding_path, self._branding)
        self.setWindowTitle(f"{self._branding.application_name} — {library_name}")
        icon_path = Path(__file__).resolve().parents[2] / "resources" / "fieldora.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        # A fixed 1100x700 logical minimum can exceed a laptop's available
        # geometry after moving from a lower-scale external monitor.
        self.setMinimumSize(QSize(640, 420))
        self._display_screen = None

        self._navigation = QTreeWidget()
        self._navigation.setHeaderHidden(True)
        self._navigation_items: dict[str, QTreeWidgetItem] = {}
        navigation = (
            (
                "Science Workspace",
                (
                    ("Overview", (
                        ("Home", "Home"),
                    )),
                    ("Research", (
                        ("Projects & Tasks", "Science Projects"),
                        ("Maritime Operations", "Maritime Operations"),
                        ("Observation Register", "Observation History"),
                        ("Dossiers", "Science Dossiers"),
                        ("Research Calendar", "Science Calendar"),
                    )),
                    ("Library", (
                        ("Media", (
                            ("Photos", "Photos"),
                            ("Sounds", "Sounds"),
                            ("Videos", "Videos"),
                        )),
                        ("Research Documents", (
                            ("Documents", "Documents"),
                            ("Whiteboards", "Science Whiteboard"),
                        )),
                        ("Collections", "Collections"),
                        ("Notebook", "Notebook"),
                        ("Maps", "Map"),
                    )),
                    ("Scientific Records", (
                        ("Animal Records", "Animal Records"),
                        ("Plants & Fungi", "Plant & Flower Records"),
                        ("Marine & Freshwater Science", "Marine & Freshwater Science"),
                        ("Other Specimens & Artifacts", "Other Science Artifacts"),
                        ("Life Lists & Statistics", "Life Lists & Statistics"),
                        ("Habitats & Seasonality", "Conservation & Seasonality"),
                    )),
                    ("Knowledge", (
                        ("Knowledge Explorer", "Knowledge Base"),
                        ("Regional Knowledge", "Regional Knowledge"),
                    )),
                    ("Analysis", (
                        ("Analysis & AI Review", "AI Review"),
                        ("Reports", "Reporting"),
                        ("Offline Scientific Maps", "Offline Maps"),
                    )),
                ),
            ),
            (
                "Platform Management",
                (
                    ("People & Governance", (
                        ("Users, Roles & Access Contracts", "Access & Contracts"),
                    )),
                    ("AI & Processing", (
                        ("Models", "Models"),
                        ("AI Configuration", "AI Resources"),
                        ("Processing Components", "Resource Components"),
                        ("Enrichment Sources", "Enrichment Sources"),
                    )),
                    ("Knowledge Configuration", (
                        ("Knowledge Sources", "Knowledge Sources"),
                        ("Taxonomy Sources", "Taxonomy Resources"),
                    )),
                    ("Integrations", (
                        ("Installed Integrations & API Connections", "Integrations"),
                    )),
                    ("Library Administration", (
                        ("Import", "Imports"),
                        ("Export", "Export"),
                        ("Enabled Modules", "Library Types"),
                        ("Storage", "Storage Manager"),
                        ("Trash & Deletion Approvals", "Trash Manager"),
                        ("Back Up Library", "__backup__"),
                        ("Restore Library", "__restore__"),
                    )),
                    ("Operations", (
                        ("Operations Center", "Activity Center"),
                        ("Health", "Health Check"),
                        ("Diagnostics", "Diagnostics"),
                        ("Updates", "Updates"),
                    )),
                    ("Appearance", (
                        ("Preferences", "Preferences"),
                        ("Branding & Identity", "Branding & Project"),
                    )),
                ),
            ),
        )

        def add_navigation_branch(
            parent: QTreeWidgetItem, label: str, children: tuple
        ) -> None:
            branch = QTreeWidgetItem([label])
            branch.setFlags(branch.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            parent.addChild(branch)
            for child_label, target in children:
                if isinstance(target, tuple):
                    add_navigation_branch(branch, child_label, target)
                    continue
                leaf = QTreeWidgetItem([child_label])
                leaf.setData(0, Qt.ItemDataRole.UserRole, target)
                branch.addChild(leaf)
                if not target.startswith("__") and target not in self._navigation_items:
                    self._navigation_items[target] = leaf
            branch.setExpanded(True)

        for root_label, branches in navigation:
            root = QTreeWidgetItem([root_label])
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._navigation.addTopLevelItem(root)
            for branch_label, children in branches:
                add_navigation_branch(root, branch_label, children)
            root.setExpanded(True)
            root.setHidden(True)
        from natureai_next.ui.qt.v5_icons import route_icon
        for label,route in (("Home","Home"),("Library","Library Overview"),("Observations","Observations Overview"),("Research","Research Overview"),("Knowledge & AI","Knowledge & AI Overview"),("Administration","Administration Overview"),("Help & Guides","Help & Guides")):
            item=QTreeWidgetItem([label]);item.setData(0,Qt.ItemDataRole.UserRole,route);item.setIcon(0,route_icon(route));self._navigation.addTopLevelItem(item);self._navigation_items[route]=item
        self._navigation.setMinimumWidth(174);self._navigation.setMaximumWidth(194)
        self._navigation.setStyleSheet("QTreeWidget{background:#11191c;border:0;color:#c7d1cd;padding:18px 6px;}QTreeWidget::item{height:44px;padding:3px 11px;font-size:14px;}QTreeWidget::item:selected{background:#234238;color:#fff;border-left:3px solid #70c78a;}QTreeWidget::item:hover{background:#1b2927;}")
        self._stack = QStackedWidget()
        self._catalog_service = catalog_service
        self._thumbnail_service = thumbnail_service
        self._viewers: set[ViewerDialog] = set()
        from natureai_next.application.enrichment_desktop import build_desktop_enrichment_controller

        self._enrichment_controller = build_desktop_enrichment_controller(
            self._enrichment_database_path, include_fixture_sound=False
        )
        self._library = LibraryWorkspace(
            catalog_service,
            thumbnail_service,
            catalog_edit_service,
            search_service,
            views_service,
            maintenance_service,
            workspace_mode="library",
            enrichment_controller=self._enrichment_controller,
        )
        self._sounds_workspace = MediaLibraryWorkspace(
            self._library_database_path,
            SOUND_SPEC,
            self,
            enrichment_controller=self._enrichment_controller,
        )
        self._videos_workspace = MediaLibraryWorkspace(
            self._library_database_path,
            VIDEO_SPEC,
            self,
            enrichment_controller=self._enrichment_controller,
        )
        self._documents_workspace = MediaLibraryWorkspace(
            self._library_database_path,
            DOCUMENT_SPEC,
            self,
            enrichment_controller=self._enrichment_controller,
        )
        self._collections_workspace = LibraryWorkspace(
            catalog_service,
            thumbnail_service,
            catalog_edit_service,
            search_service,
            views_service,
            maintenance_service,
            workspace_mode="collections",
        )
        from natureai_next.bootstrap.paths import resolve_application_paths

        self._trash_manager_workspace = (
            TrashManagerWorkspace(
                self._library_database_path,
                maintenance_service,
                self,
                approval_database_path=(
                    resolve_application_paths().subsystem_databases_dir
                    / "deletion-approvals.sqlite3"
                ),
                access_database_path=(
                    resolve_application_paths().subsystem_databases_dir
                    / "access-control.sqlite3"
                ),
            )
            if maintenance_service is not None
            else self._placeholder("Trash Manager", "Trash maintenance is unavailable.")
        )
        self._storage_manager_workspace = StorageManagerWorkspace(self._library_database_path, self)
        self._preferences_workspace = StoragePreferencesWorkspace(self)
        self._notebook_workspace = NotebookWorkspace(
            store_path=session_path.parent / "notebook.json",
            selected_asset_ids=self._library.selected_asset_ids,
            parent=self,
        )
        science_database = (
            resolve_application_paths().subsystem_databases_dir / "science.sqlite3"
        )
        from natureai_next.application.local_profiles import provision_project_access
        provision_project_access(
            science_database,
            os.environ.get("FIELDORA_IDENTITY_ID", "viewer"),
            os.environ.get("FIELDORA_PROFILE_ROLE", "viewer"),
        )
        from natureai_next.application.science import (
            ScienceSession,
            default_science_snapshot,
        )
        from natureai_next.infrastructure.database.science import (
            SqliteScienceRepository,
        )

        science_session = ScienceSession(
            SqliteScienceRepository(science_database, default_science_snapshot)
        )
        from natureai_next.application.access_control import AccessAdministrationService
        from natureai_next.infrastructure.database.access_control import (
            SqliteAccessControlRepository,
        )
        from natureai_next.ui.qt.access_control import AccessControlWorkspace

        self._access_control_workspace = AccessControlWorkspace(
            AccessAdministrationService(
                SqliteAccessControlRepository(
                    resolve_application_paths().subsystem_databases_dir
                    / "access-control.sqlite3"
                )
            ),
            self,
        )
        self._v5_selected_asset_ids: tuple[str, ...] = ()
        def selected_science_media() -> tuple[str, ...]:
            return tuple(
                dict.fromkeys(
                    self._library.selected_asset_ids()
                    + self._sounds_workspace.selected_asset_ids()
                    + self._videos_workspace.selected_asset_ids()
                    + self._documents_workspace.selected_asset_ids()
                    + tuple(getattr(self, "_v5_selected_asset_ids", ()))
                )
            )
        self._science_workspaces = {
            route: ScienceWorkspace(
                science_database,
                selected_asset_ids=selected_science_media,
                section=section,
                science_session=science_session,
                library_database_path=self._library_database_path,
                parent=self,
            )
            for route, section in {
                "Science Projects": "projects",
                "Science Dossiers": "dossiers",
                "Animal Records": "animals",
                "Plant & Flower Records": "plants",
                "Other Science Artifacts": "other_artifacts",
                "Science Whiteboard": "whiteboard",
                "Science Calendar": "calendar",
            }.items()
        }
        for workspace in self._science_workspaces.values():
            workspace.route_requested.connect(self._select_workspace)

        marine_maritime_database = (
            resolve_application_paths().subsystem_databases_dir
            / "marine-maritime.sqlite3"
        )
        self._marine_maritime_workspaces = {
            "Marine & Freshwater Science": MarineMaritimeWorkspace(
                marine_maritime_database,
                domain="marine",
                selected_asset_ids=selected_science_media,
                parent=self,
            ),
            "Maritime Operations": MarineMaritimeWorkspace(
                marine_maritime_database,
                domain="maritime",
                selected_asset_ids=selected_science_media,
                parent=self,
            ),
        }
        self._home_workspace = HomeWorkspace(
            library_name=library_name,
            library_database=self._library_database_path,
            science_database=science_database,
            marine_maritime_database=marine_maritime_database,
            parent=self,
        )
        self._home_workspace.route_requested.connect(self._select_workspace)
        self._legacy_home_workspace = self._home_workspace
        from natureai_next.ui.qt.v5_desktop import build_pages
        self._v5_pages=build_pages(library_database=self._library_database_path,science_database=science_database,enrichment_database=self._enrichment_database_path,parent=self)
        for page in self._v5_pages.values():page.route_requested.connect(self._select_workspace)
        self._home_workspace=self._v5_pages["Home"]
        from natureai_next.application.components import ResourceComponentRegistry

        self._component_registry = ResourceComponentRegistry()
        from natureai_next.ui.qt.gbif_taxonomy import GbifTaxonomyWorkspace

        self._gbif_taxonomy_workspace = GbifTaxonomyWorkspace(
            library_database=self._library_database_path,
            selected_asset_ids=lambda: tuple(
                dict.fromkeys(
                    self._library.selected_asset_ids()
                    + self._collections_workspace.selected_asset_ids()
                )
            ),
            component_registry=self._component_registry,
            parent=self,
        )
        self._library.viewer_requested.connect(self._open_viewer)
        self._collections_workspace.viewer_requested.connect(self._open_viewer)
        self._stack.addWidget(self._library)
        self._stack.addWidget(self._sounds_workspace)
        self._stack.addWidget(self._videos_workspace)
        self._stack.addWidget(self._documents_workspace)
        self._ai_review_workspace = ai_review_workspace_factory(self._library.selected_asset_ids)
        self._ai_review_workspace._components = self._component_registry
        self._ai_review_workspace.resources_requested.connect(self.open_ai_resources)
        self._ai_review_workspace.observation_requested.connect(self.open_observation_history)
        from natureai_next.ui.qt.activity import ActivityCenterWidget
        from natureai_next.ui.qt.ecology import EcologicalContextWorkspace
        from natureai_next.ui.qt.health import HealthCheckWidget
        from natureai_next.ui.qt.observation_statistics import ObservationStatisticsWorkspace
        from natureai_next.ui.qt.observations import ObservationHistoryWorkspace
        from natureai_next.ui.qt.product_pages import (
            AboutDialog,
            BrandingWorkspace,
            DiagnosticsWorkspace,
        )
        from natureai_next.ui.qt.settings_pages import (
            AIResourcesWorkspace,
            IntegrationsWorkspace,
            LibraryTypesWorkspace,
            OfflineMapsResourcesWorkspace,
            RegionalKnowledgeWorkspace,
            ResourceComponentsWorkspace,
            TaxonomyResourcesWorkspace,
        )

        self._activity_workspace = ActivityCenterWidget(self)
        from natureai_next.ui.qt.activity import activity_center
        from natureai_next.ui.qt.reporting import ExportWorkspace, ReportingWorkspace

        def selection_provider():
            return tuple(
                dict.fromkeys(
                    self._library.selected_asset_ids()
                    + self._collections_workspace.selected_asset_ids()
                    + self._v5_selected_asset_ids
                )
            )

        self._export_workspace = ExportWorkspace(
            self._library_database_path, selection_provider, activity_center(), self
        )
        self._reporting_workspace = ReportingWorkspace(
            self._library_database_path, selection_provider, activity_center(), self
        )
        observation_service = self._ai_review_workspace.observation_service
        if observation_service is None:
            raise RuntimeError(
                "Observation Intelligence service is required for the desktop workspace"
            )
        self._observation_workspace = ObservationHistoryWorkspace(
            service=observation_service,
            thumbnails=thumbnail_service,
            ecology_service=self._ai_review_workspace.ecology_service,
            knowledge_engine=self._ai_review_workspace.knowledge_engine,
            enrichment_controller=self._enrichment_controller,
            parent=self,
        )
        self._observation_workspace.viewer_requested.connect(self._open_viewer)
        self._observation_workspace.knowledge_requested.connect(self.open_knowledge_center)
        self._observation_statistics_workspace = ObservationStatisticsWorkspace(
            service=observation_service, parent=self
        )
        ecology_service = self._ai_review_workspace.ecology_service
        if ecology_service is None:
            raise RuntimeError("Ecological context service is required for the desktop workspace")
        self._ecology_workspace = EcologicalContextWorkspace(ecology_service, parent=self)
        self._ai_resources_workspace = AIResourcesWorkspace(
            resource_service=self._ai_review_workspace.resource_service,
            suggestion_service=self._ai_review_workspace.suggestion_service,
            regional_service=self._ai_review_workspace.regional_service,
            regional_acquisition_service=self._ai_review_workspace.regional_acquisition_service,
            activity_open=self.open_activity_center,
            resources_ready=self._on_ai_resources_ready,
            parent=self,
        )
        self._regional_workspace = RegionalKnowledgeWorkspace(
            regional_service=self._ai_review_workspace.regional_service,
            regional_acquisition_service=self._ai_review_workspace.regional_acquisition_service,
            parent=self,
        )
        self._offline_maps_resources_workspace = OfflineMapsResourcesWorkspace(
            open_manager=self.open_offline_map_setup,
            parent=self,
        )
        self._taxonomy_resources_workspace = TaxonomyResourcesWorkspace(
            resource_service=self._ai_review_workspace.resource_service,
            configure_regional=self._ai_resources_workspace.open_regional_setup,
            open_advanced=self._ai_resources_workspace.open_advanced_resources,
            activity_open=self.open_activity_center,
            resources_ready=self._on_ai_resources_ready,
            parent=self,
        )
        self._library_types_workspace = LibraryTypesWorkspace(
            self._library_database_path,
            self,
            science_database_path=science_database,
        )
        self._library_types_workspace.capabilities_changed.connect(
            self._refresh_library_type_navigation
        )
        self._integrations_workspace = IntegrationsWorkspace(self._library_database_path, self)
        from natureai_next.infrastructure.ai.dynamic_model_manager import DynamicModelManager
        from natureai_next.infrastructure.ai.model_catalog import ModelCatalog
        from natureai_next.ui.qt.model_manager import ModelManagerWorkspace

        model_catalog_path = Path(__file__).resolve().parents[2] / "resources" / "models.json"
        from natureai_next.bootstrap.paths import resolve_application_paths

        self._dynamic_model_manager = DynamicModelManager(
            ModelCatalog.load(model_catalog_path),
            resolve_application_paths().models_dir / "runtime",
            capability_router=self._enrichment_controller.capability_router,
        )
        self._models_workspace = ModelManagerWorkspace(self._dynamic_model_manager, self)
        from natureai_next.ui.qt.knowledge_sources import KnowledgeSourcesWorkspace

        self._knowledge_sources_workspace = KnowledgeSourcesWorkspace(self)
        self._knowledge_sources_workspace.route_requested.connect(self._select_workspace)
        self._resource_components_workspace = ResourceComponentsWorkspace(
            self._component_registry, self
        )
        from natureai_next import __version__
        from natureai_next.application.enrichment_retention_ui import EnrichmentRetentionController
        from natureai_next.application.source_lifecycle import SourceRegistryService
        from natureai_next.bootstrap.paths import resolve_application_paths
        from natureai_next.plugin_api import PLUGIN_API_VERSION
        from natureai_next.plugins.bundles import OfflineBundleInstaller
        from natureai_next.ui.qt.source_manager import EnrichmentSourceManagerWorkspace

        source_registry = SourceRegistryService(self._enrichment_database_path)
        from uuid import uuid4

        from natureai_next.application.source_lifecycle import SourceRecord, SourceState
        from natureai_next.application.source_workspace import SourceWorkspaceService
        from natureai_next.synthesis_core import create_builtin_source_router

        builtin_source_router = create_builtin_source_router()
        for descriptor in builtin_source_router.discover():
            try:
                source_registry.get(descriptor.source_id)
            except KeyError:
                source_registry.register(
                    SourceRecord(
                        source_id=descriptor.source_id,
                        kind="source",
                        display_name=descriptor.display_name,
                        version=descriptor.version,
                        state=SourceState.OFFLINE,
                    )
                )
        source_workspace = SourceWorkspaceService(
            self._enrichment_database_path,
            builtin_source_router,
            id_factory=lambda: str(uuid4()),
        )
        self._enrichment_sources_workspace = EnrichmentSourceManagerWorkspace(
            source_registry,
            self,
            bundle_installer=OfflineBundleInstaller(
                resolve_application_paths().plugins_dir,
                source_registry,
                api_version=PLUGIN_API_VERSION,
                application_version=__version__,
            ),
            retention_controller=EnrichmentRetentionController(self._enrichment_database_path),
            source_workspace=source_workspace,
        )
        self._enrichment_sources_workspace.sources_changed.connect(self._sounds_workspace.refresh)
        self._enrichment_sources_workspace.sources_changed.connect(self._videos_workspace.refresh)
        self._enrichment_sources_workspace.sources_changed.connect(
            self._documents_workspace.refresh
        )
        self._enrichment_sources_workspace.sources_changed.connect(self._library.refresh)
        self._resource_components_workspace.components_changed.connect(
            self._gbif_taxonomy_workspace.refresh
        )
        self._resource_components_workspace.components_changed.connect(
            self._ai_review_workspace.refresh
        )
        self._health_workspace = HealthCheckWidget(health_service, self)
        self._health_workspace.backup_requested.connect(self.back_up_library)
        self._health_workspace.restore_requested.connect(self.restore_library)
        self._health_workspace.updates_requested.connect(self.check_for_updates)
        self._branding_workspace = BrandingWorkspace(
            self._branding_path, self._branding_store, self
        )
        self._branding_workspace.branding_changed.connect(self._apply_branding)
        self._diagnostics_workspace = DiagnosticsWorkspace(
            library_name=library_name,
            session_path=session_path,
            branding_path=self._branding_path,
            branding_store=self._branding_store,
            resource_service=self._ai_review_workspace.suggestion_service,
            ecology_service=ecology_service,
            parent=self,
        )
        self._about_dialog_factory = lambda: AboutDialog(
            branding=self._branding_store.load(self._branding_path),
            diagnostics=self._diagnostics_workspace,
            parent=self,
        )
        self._map_workspace_factory = map_workspace_factory
        self._knowledge_center_workspace_factory = knowledge_center_workspace_factory
        self._reference_knowledge_workspace: QWidget | None = None
        if knowledge_center_workspace_factory is not None:
            self._reference_knowledge_workspace = knowledge_center_workspace_factory()
            if hasattr(self._reference_knowledge_workspace, "observation_history_requested"):
                self._reference_knowledge_workspace.observation_history_requested.connect(
                    self._open_observation_taxon
                )
        from natureai_next.ui.qt.knowledge_base import KnowledgeBaseWorkspace

        self._knowledge_base_workspace = KnowledgeBaseWorkspace(
            library_database=self._library_database_path,
            enrichment_database=self._enrichment_database_path,
            ai_review=self._ai_review_workspace,
            enrichment_controller=self._enrichment_controller,
            gbif_taxonomy=self._gbif_taxonomy_workspace,
            reference_taxonomy=self._reference_knowledge_workspace,
            parent=self,
        )
        self._knowledge_center_workspace = self._knowledge_base_workspace
        self._map_workspace: QWidget | None = None
        self._imports = ImportWorkspace(import_service)
        self._imports.import_finished.connect(self._on_import_finished)
        self._stack.addWidget(self._imports)
        for name in self.WORKSPACES[5:]:
            if name == "Map":
                self._stack.addWidget(
                    self._placeholder(
                        "Map", "Open this workspace to activate the optional offline-map subsystem."
                    )
                )
                continue
            if name == "Export":
                self._stack.addWidget(self._export_workspace)
                continue
            if name == "Reporting":
                self._stack.addWidget(self._reporting_workspace)
                continue
            if name == "Knowledge Base":
                self._stack.addWidget(self._knowledge_base_workspace)
                continue
            if name == "Collections":
                self._stack.addWidget(self._collections_workspace)
            elif name == "Notebook":
                self._stack.addWidget(self._notebook_workspace)
            elif name in self._science_workspaces:
                self._stack.addWidget(self._science_workspaces[name])
            elif name in self._marine_maritime_workspaces:
                self._stack.addWidget(self._marine_maritime_workspaces[name])
            elif name == "Activity Center":
                self._stack.addWidget(self._activity_workspace)
            elif name == "Observation History":
                self._stack.addWidget(self._observation_workspace)
            elif name == "Life Lists & Statistics":
                self._stack.addWidget(self._observation_statistics_workspace)
            elif name == "Conservation & Seasonality":
                self._stack.addWidget(self._ecology_workspace)
            elif name == "AI Resources":
                self._stack.addWidget(self._ai_resources_workspace)
            elif name == "Regional Knowledge":
                self._stack.addWidget(self._regional_workspace)
            elif name == "Offline Maps":
                self._stack.addWidget(self._offline_maps_resources_workspace)
            elif name == "Taxonomy Resources":
                self._stack.addWidget(self._taxonomy_resources_workspace)
            elif name == "Library Types":
                self._stack.addWidget(self._library_types_workspace)
            elif name == "Access & Contracts":
                self._stack.addWidget(self._access_control_workspace)
            elif name == "Integrations":
                self._stack.addWidget(self._integrations_workspace)
            elif name == "Models":
                self._stack.addWidget(self._models_workspace)
            elif name == "Knowledge Sources":
                self._stack.addWidget(self._knowledge_sources_workspace)
            elif name == "Resource Components":
                self._stack.addWidget(self._resource_components_workspace)
            elif name == "Enrichment Sources":
                self._stack.addWidget(self._enrichment_sources_workspace)
            elif name == "Trash Manager":
                self._stack.addWidget(self._trash_manager_workspace)
            elif name == "Storage Manager":
                self._stack.addWidget(self._storage_manager_workspace)
            elif name == "Home":
                self._stack.addWidget(self._home_workspace)
            elif name in self._v5_pages:
                self._stack.addWidget(self._v5_pages[name])
            elif name == "Preferences":
                self._stack.addWidget(self._preferences_workspace)
            elif name == "Health Check":
                self._stack.addWidget(self._health_workspace)
            elif name == "Branding & Project":
                self._stack.addWidget(self._branding_workspace)
            elif name == "Diagnostics":
                self._stack.addWidget(self._diagnostics_workspace)
            else:
                self._stack.addWidget(
                    self._placeholder(name, "Workspace not yet connected to the desktop shell.")
                )
        self.setCentralWidget(self._stack)

        self._navigation_dock = QDockWidget("Navigation", self)
        self._navigation_dock.setObjectName("navigationDock")
        self._navigation_dock.setWidget(self._navigation)
        self._navigation_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self._navigation_dock.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )
        from natureai_next.ui.qt.v5_icons import icon
        brand=QWidget();brand.setStyleSheet("background:#11191c;");brand_layout=QHBoxLayout(brand);brand_layout.setContentsMargins(15,13,10,10);mark=QLabel();mark.setPixmap(icon('fieldora-logo').pixmap(27,27));word=QLabel('Fieldora');word.setStyleSheet('color:#f4f8f5;font-size:21px;font-weight:700;');brand_layout.addWidget(mark);brand_layout.addWidget(word);brand_layout.addStretch();self._navigation_dock.setTitleBarWidget(brand)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._navigation_dock)

        self._inspector_dock = QDockWidget("Inspector", self)
        self._inspector_dock.setObjectName("inspectorDock")
        self._inspector_dock.setWidget(QLabel("No selection"))
        self._inspector_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self._inspector_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._inspector_dock)
        self._inspector_dock.setVisible(self._session.inspector_visible)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Offline • Ready")
        from natureai_next.ui.qt.activity import activity_center

        self._activity_center = activity_center()
        self._exit_after_tasks = False
        self._activity_button = QPushButton("Operations Center")
        self._activity_button.setFlat(True)
        self._activity_button.clicked.connect(self.open_activity_center)
        self.statusBar().addPermanentWidget(self._activity_button)
        self._activity_center.changed.connect(self._activity_status_changed)
        self._activity_status_changed()
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(toolbar)
        toolbar.setVisible(False)

        self._import_action = QAction("Import…", self)
        self._import_action.setShortcut(QKeySequence("Ctrl+I"))
        self._import_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._import_action.triggered.connect(self.open_import_folder)
        self.addAction(self._import_action)
        toolbar.addAction(self._import_action)

        self._export_action = QAction("Export…", self)
        self._export_action.setShortcut(QKeySequence("Ctrl+E"))
        self._export_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._export_action.triggered.connect(lambda: self._select_workspace("Export"))
        self.addAction(self._export_action)
        toolbar.addAction(self._export_action)

        self._backup_action = QAction("Back Up Library…", self)
        self._backup_action.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self._backup_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._backup_action.setToolTip("Create a verified backup of the current Aperture library database")
        self._backup_action.triggered.connect(self.back_up_library)
        self.addAction(self._backup_action)
        toolbar.addAction(self._backup_action)

        self._restore_action = QAction("Restore Library…", self)
        self._restore_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self._restore_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._restore_action.setToolTip("Verify and stage restoration of an Aperture library backup")
        self._restore_action.triggered.connect(self.restore_library)
        self.addAction(self._restore_action)
        toolbar.addAction(self._restore_action)
        toolbar.addSeparator()

        activity_action = QAction("Operations Center", self)
        activity_action.triggered.connect(self.open_activity_center)
        toolbar.addAction(activity_action)

        self._shutdown_action = QAction("Shutdown", self)
        self._shutdown_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._shutdown_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shutdown_action.triggered.connect(self.close)
        self.addAction(self._shutdown_action)

        self._verify_backup_action = QAction("Verify Backup…", self)
        self._verify_backup_action.triggered.connect(self.verify_backup)
        self._manage_backups_action = QAction("Manage Backups…", self)
        self._manage_backups_action.triggered.connect(self.manage_backups)
        self._check_updates_action = QAction("Check for Updates…", self)
        self._check_updates_action.triggered.connect(self.check_for_updates)

        def add_workspace_actions(menu: QMenu, entries: tuple[tuple[str, str], ...]) -> None:
            for label, route in entries:
                action = QAction(label, self)
                action.triggered.connect(
                    lambda checked=False, name=route: self._select_workspace(name)
                )
                menu.addAction(action)

        file_menu: QMenu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._import_action)
        file_menu.addAction(self._export_action)
        file_menu.addSeparator()
        file_menu.addAction(self._backup_action)
        file_menu.addAction(self._restore_action)
        file_menu.addSeparator()
        file_menu.addAction(self._shutdown_action)

        research_menu: QMenu = self.menuBar().addMenu("&Research")
        add_workspace_actions(
            research_menu,
            (
                ("Projects & Tasks", "Science Projects"),
                ("Maritime Operations", "Maritime Operations"),
                ("Observation Register", "Observation History"),
                ("Dossiers", "Science Dossiers"),
                ("Research Calendar", "Science Calendar"),
                ("Habitats & Seasonality", "Conservation & Seasonality"),
            ),
        )
        records_menu = research_menu.addMenu("Scientific Records")
        add_workspace_actions(
            records_menu,
            (
                ("Animal Records", "Animal Records"),
                ("Plants & Fungi", "Plant & Flower Records"),
                ("Marine & Freshwater Science", "Marine & Freshwater Science"),
                ("Other Specimens & Artifacts", "Other Science Artifacts"),
                ("Life Lists & Statistics", "Life Lists & Statistics"),
            ),
        )

        data_menu: QMenu = self.menuBar().addMenu("&Data")
        media_menu = data_menu.addMenu("Media")
        add_workspace_actions(
            media_menu,
            (
                ("Photos", "Photos"),
                ("Sounds", "Sounds"),
                ("Videos", "Videos"),
            ),
        )
        documents_menu = data_menu.addMenu("Research Documents")
        add_workspace_actions(
            documents_menu,
            (
                ("Documents", "Documents"),
                ("Whiteboards", "Science Whiteboard"),
            ),
        )
        add_workspace_actions(
            data_menu,
            (
                ("Collections", "Collections"),
                ("Notebook", "Notebook"),
                ("Maps", "Map"),
            ),
        )

        analyse_menu: QMenu = self.menuBar().addMenu("&Analyse")
        add_workspace_actions(
            analyse_menu,
            (
                ("Analysis & AI Review", "AI Review"),
                ("Knowledge Explorer", "Knowledge Base"),
                ("Regional Knowledge", "Regional Knowledge"),
                ("Taxonomy", "Taxonomy"),
                ("Reports", "Reporting"),
                ("Offline Scientific Maps", "Offline Maps"),
            ),
        )

        collaborate_menu: QMenu = self.menuBar().addMenu("&Collaborate")
        add_workspace_actions(
            collaborate_menu,
            (
                ("Project Tasks & Assignments", "Science Projects"),
                ("AI Review Queue", "AI Review"),
                ("Users, Roles & Access Contracts", "Access & Contracts"),
                ("Operations & Notifications", "Activity Center"),
            ),
        )

        platform_menu: QMenu = self.menuBar().addMenu("&Platform")
        governance_menu = platform_menu.addMenu("People & Governance")
        add_workspace_actions(
            governance_menu,
            (("Users, Roles & Access Contracts", "Access & Contracts"),),
        )
        ai_menu = platform_menu.addMenu("AI & Processing")
        add_workspace_actions(
            ai_menu,
            (
                ("Models", "Models"),
                ("AI Configuration", "AI Resources"),
                ("Processing Components", "Resource Components"),
                ("Enrichment Sources", "Enrichment Sources"),
            ),
        )
        knowledge_configuration_menu = platform_menu.addMenu("Knowledge Configuration")
        add_workspace_actions(
            knowledge_configuration_menu,
            (
                ("Knowledge Sources", "Knowledge Sources"),
                ("Taxonomy Sources", "Taxonomy Resources"),
            ),
        )
        integrations_menu = platform_menu.addMenu("Integrations")
        add_workspace_actions(
            integrations_menu,
            (("Installed Integrations & API Connections", "Integrations"),),
        )
        library_administration_menu = platform_menu.addMenu("Library Administration")
        add_workspace_actions(
            library_administration_menu,
            (
                ("Import", "Imports"),
                ("Export", "Export"),
                ("Enabled Modules", "Library Types"),
                ("Storage", "Storage Manager"),
                ("Trash & Deletion Approvals", "Trash Manager"),
            ),
        )
        library_administration_menu.addSeparator()
        library_administration_menu.addAction(self._verify_backup_action)
        library_administration_menu.addAction(self._manage_backups_action)
        operations_menu = platform_menu.addMenu("Operations")
        add_workspace_actions(
            operations_menu,
            (
                ("Operations Center", "Activity Center"),
                ("Health", "Health Check"),
                ("Diagnostics", "Diagnostics"),
                ("Updates", "Updates"),
            ),
        )
        operations_menu.addSeparator()
        operations_menu.addAction(self._check_updates_action)
        appearance_menu = platform_menu.addMenu("Appearance")
        add_workspace_actions(
            appearance_menu,
            (
                ("Preferences", "Preferences"),
                ("Branding & Identity", "Branding & Project"),
            ),
        )
        platform_menu.addSeparator()
        platform_menu.addAction(self._navigation_dock.toggleViewAction())
        platform_menu.addAction(self._inspector_dock.toggleViewAction())
        reset_layout = QAction("Reset Workspace Layout", self)
        reset_layout.triggered.connect(self.reset_workspace_layout)
        platform_menu.addAction(reset_layout)

        help_menu: QMenu = self.menuBar().addMenu("&Help")
        manuals_action = QAction("Fieldora Manuals…", self)
        manuals_action.triggered.connect(self.open_manuals)
        help_menu.addAction(manuals_action)
        user_guide_action = QAction("User Guide…", self)
        user_guide_action.triggered.connect(lambda: self.open_help_topic("user-guide"))
        help_menu.addAction(user_guide_action)
        vision_action = QAction("Vision", self)
        vision_action.triggered.connect(lambda: self.open_help_topic("vision"))
        help_menu.addAction(vision_action)
        whats_new_action = QAction("What's New", self)
        whats_new_action.triggered.connect(lambda: self.open_help_topic("release-notes"))
        help_menu.addAction(whats_new_action)
        troubleshooting_action = QAction("Troubleshooting", self)
        troubleshooting_action.triggered.connect(lambda: self.open_help_topic("troubleshooting"))
        help_menu.addAction(troubleshooting_action)
        help_menu.addSeparator()
        self._shortcuts_action = QAction("Keyboard Shortcuts…", self)
        self._shortcuts_action.setShortcut(QKeySequence("Ctrl+/"))
        self._shortcuts_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcuts_action.triggered.connect(self.open_keyboard_shortcuts)
        self.addAction(self._shortcuts_action)
        help_menu.addAction(self._shortcuts_action)
        self._context_help_action = QAction("Help for Current Screen", self)
        self._context_help_action.setShortcut(QKeySequence("F1"))
        self._context_help_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._context_help_action.triggered.connect(self.open_context_help)
        self.addAction(self._context_help_action)
        help_menu.addAction(self._context_help_action)
        help_menu.addSeparator()
        self._about_action = QAction(f"About {self._branding.application_name}…", self)
        self._about_action.triggered.connect(self.open_about)
        help_menu.addAction(self._about_action)
        self.menuBar().setVisible(False)

        self._navigation.itemClicked.connect(self._workspace_item_clicked)
        self._refresh_library_type_navigation()
        self._select_workspace("Home")
        if self._session.window_geometry_b64:
            self.restoreGeometry(
                QByteArray.fromBase64(self._session.window_geometry_b64.encode("ascii"))
            )
        self.apply_accessibility_defaults()
        # Core panes use a deterministic docked layout. Arbitrary Qt dock-state
        # restoration can resurrect a pane as a detached top-level window after
        # upgrades or display changes, so only window geometry is persisted.

    def bind_per_monitor_display_scaling(self) -> None:
        """Track the native window as Windows moves it between DPI domains."""
        handle = self.windowHandle()
        if handle is None:
            QTimer.singleShot(0, self.bind_per_monitor_display_scaling)
            return
        with contextlib.suppress(Exception):
            handle.screenChanged.disconnect(self._screen_changed)
        handle.screenChanged.connect(self._screen_changed)
        self._screen_changed(handle.screen())

    @Slot(object)
    def _screen_changed(self, screen) -> None:
        previous = self._display_screen
        if previous is not None and previous is not screen:
            with contextlib.suppress(Exception):
                previous.logicalDotsPerInchChanged.disconnect(self._schedule_display_adaptation)
            with contextlib.suppress(Exception):
                previous.availableGeometryChanged.disconnect(self._schedule_display_adaptation)
        self._display_screen = screen
        if screen is not None:
            with contextlib.suppress(Exception):
                screen.logicalDotsPerInchChanged.connect(
                    self._schedule_display_adaptation, Qt.ConnectionType.UniqueConnection
                )
            with contextlib.suppress(Exception):
                screen.availableGeometryChanged.connect(
                    self._schedule_display_adaptation, Qt.ConnectionType.UniqueConnection
                )
        self._schedule_display_adaptation()

    @Slot()
    def _schedule_display_adaptation(self, *_args) -> None:
        # Windows completes WM_DPICHANGED after screenChanged; defer geometry
        # fitting until Qt has adopted the destination screen's logical DPI.
        QTimer.singleShot(0, self._adapt_to_current_screen)

    def _adapt_to_current_screen(self) -> None:
        handle = self.windowHandle()
        screen = handle.screen() if handle is not None else self._display_screen
        if screen is None:
            return
        available = screen.availableGeometry()
        minimum = adaptive_minimum_size(available.width(), available.height())
        self.setMinimumSize(QSize(*minimum))
        if not self.isMaximized() and not self.isFullScreen():
            current = self.geometry()
            fitted = fit_window_geometry(
                (current.x(), current.y(), current.width(), current.height()),
                (available.x(), available.y(), available.width(), available.height()),
            )
            if fitted != (current.x(), current.y(), current.width(), current.height()):
                self.setGeometry(*fitted)
        layout = self.centralWidget().layout() if self.centralWidget() is not None else None
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.updateGeometry()

    @Slot()
    def open_offline_map_setup(self) -> None:
        if self._offline_map_setup_factory is None:
            QMessageBox.critical(
                self,
                "Offline map setup unavailable",
                "The offline-map workflow was not composed by the application launcher.",
            )
            return
        self._offline_map_setup_factory(self).exec()

    def open_keyboard_shortcuts(self) -> None:
        from natureai_next.ui.qt.accessibility import KeyboardShortcutsDialog

        KeyboardShortcutsDialog(self).exec()

    def open_help_topic(self, topic_id: str) -> None:
        from natureai_next.ui.qt.help_system import HelpBrowserDialog

        HelpBrowserDialog(self, initial_topic=topic_id).exec()

    def open_manuals(self) -> None:
        from natureai_next.ui.qt.manuals_app import FieldoraManualsWindow

        self._manuals_window = FieldoraManualsWindow()
        self._manuals_window.show()
        self._manuals_window.raise_()
        self._manuals_window.activateWindow()

    def open_context_help(self) -> None:
        from natureai_next.ui.qt.help_system import WORKSPACE_TOPIC

        workspace = self.WORKSPACES[self._stack.currentIndex()]
        self.open_help_topic(WORKSPACE_TOPIC.get(workspace, "user-guide"))

    def apply_accessibility_defaults(self) -> int:
        from natureai_next.ui.qt.accessibility import apply_accessibility_defaults

        return apply_accessibility_defaults(self)

    @staticmethod
    def _placeholder(title: str, detail: str) -> QWidget:
        label = QLabel(f"<h2>{title}</h2><p>{detail}</p>")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    @Slot(object, int)
    def _workspace_item_clicked(self, item: object, _column: int) -> None:
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(name, str):
            return
        if name == "__help__" or name == "__manuals__":
            self.open_manuals()
            return
        if name == "__shortcuts__":
            self.open_keyboard_shortcuts()
            return
        if name.startswith("__help_topic__:"):
            self.open_help_topic(name.partition(":")[2])
            return
        if name in getattr(self,"_v5_pages",{}):
            self._v5_pages[name].refresh()
            self._inspector_dock.setVisible(False)
        if name == "AI Review":
            name = "Knowledge Base"
            self._knowledge_base_workspace.show_ai_review()
        if name == "__backup__":
            self.back_up_library()
            return
        if name == "__restore__":
            self.restore_library()
            return
        if (
            name == "Map"
            and self._map_workspace is None
            and self._map_workspace_factory is not None
        ):
            index = self.WORKSPACES.index("Map")
            placeholder = self._stack.widget(index)
            self._map_workspace = self._map_workspace_factory()
            self._stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self._stack.insertWidget(index, self._map_workspace)
        current = self._stack.currentWidget()
        if hasattr(current, "deactivate"):
            current.deactivate()
        target = (
            self._collections_workspace
            if name == "Collections"
            else self._stack.widget(self.WORKSPACES.index(name))
        )
        self._stack.setCurrentWidget(target)
        if hasattr(target, "activate"):
            target.activate()
        if name == "Knowledge Base":
            self.statusBar().showMessage(
                "Knowledge Base • multimodal AI Review • independent taxonomy • F1 help"
            )
        else:
            self.statusBar().showMessage(f"{name} • F1 help", 8000)

    @Slot(str)
    def open_knowledge_center(self, taxon_public_id: str) -> None:
        self._select_workspace("Knowledge Base")
        if self._knowledge_center_workspace is not None and hasattr(
            self._knowledge_center_workspace, "show_taxon"
        ):
            self._knowledge_center_workspace.show_taxon(taxon_public_id, local_identity=True)

    @Slot(str)
    def _open_observation_taxon(self, taxon_public_id: str) -> None:
        self._select_workspace("Observation History")
        self._observation_workspace.show_taxon(taxon_public_id)

    @Slot()
    def _on_ai_resources_ready(self) -> None:
        """Refresh AI state and run classification for the retained Library selection."""
        self._ai_review_workspace.refresh()
        selected = self._library.selected_asset_ids()
        self._select_workspace("Knowledge Base")
        self._knowledge_base_workspace.show_ai_review()
        if selected and not self._ai_review_workspace.generation_busy:
            self._ai_review_workspace.generate_selected()

    def _select_workspace(self, name: str) -> None:
        from natureai_next.ui.qt.navigation_contracts import normalize_route

        if self._handle_v5_context_route(name):
            return
        original_name = name
        if name == "AI Review":
            self._knowledge_base_workspace.show_ai_review()
        elif name == "Taxonomy":
            self._knowledge_base_workspace.show_taxonomy()
        name = normalize_route(name)
        item = self._navigation_items.get(name)
        if item is not None and item.isHidden():
            QMessageBox.information(self, "Module disabled", f"{name} is disabled by an administrator.")
            return
        if item is not None:
            self._navigation.setCurrentItem(item)
            self._workspace_item_clicked(item, 0)
            return

        # Some V5 workspaces are intentionally opened from dashboard tiles and
        # are not represented by a sidebar item.  Route those pages directly
        # through the workspace stack instead of silently dropping the click.
        if name in self.WORKSPACES:
            if name in getattr(self, "_v5_pages", {}):
                self._v5_pages[name].refresh()
            current = self._stack.currentWidget()
            if hasattr(current, "deactivate"):
                current.deactivate()
            target = getattr(self, "_v5_pages", {}).get(name)
            if target is None:
                target = self._stack.widget(self.WORKSPACES.index(name))
            self._stack.setCurrentWidget(target)
            if hasattr(target, "activate"):
                target.activate()
            if name in getattr(self, "_v5_pages", {}):
                self._inspector_dock.setVisible(False)
            self.statusBar().showMessage(f"{name} • F1 help", 8000)
            return

        message = f"No workspace is registered for route: {name}"
        self.statusBar().showMessage(message, 12000)
        if os.environ.get("FIELDORA_STRICT_ROUTES") == "1":
            raise LookupError(message)
        QMessageBox.warning(self, "Navigation unavailable", message)

    def _handle_v5_context_route(self, route: str) -> bool:
        """Resolve V5 actions while retaining the selected domain identity."""
        if route in ("__help__", "__manuals__"):
            self.open_manuals()
            return True
        if route == "__shortcuts__":
            self.open_keyboard_shortcuts()
            return True
        if route == "__backup__":
            self.back_up_library()
            return True
        if route == "__restore__":
            self.restore_library()
            return True
        if route.startswith("__help_topic__:"):
            self.open_help_topic(route.partition(":")[2])
            return True
        if route.startswith("__help_search__:"):
            from natureai_next.ui.qt.help_system import HelpBrowserDialog
            query = route.partition(":")[2]
            dialog = HelpBrowserDialog(self)
            dialog._search.setText(query)
            dialog.exec()
            return True
        if route == "__observation_new__":
            self._select_workspace("Library Overview")
            QMessageBox.information(
                self, "New observation",
                "Select or import evidence, then use its enrichment/observation action to add location, measurements and an identification."
            )
            return True
        prefixes = (
            "__asset_collection__:", "__asset_export__:", "__asset_open__:",
            "__observation_evidence__:", "__observation_map__:", "__observation_record__:",
            "__project_open__:", "__project_map__:", "__project_surveys__:", "__project_measurements__:", "__project_quality__:",
        )
        prefix = next((value for value in prefixes if route.startswith(value)), None)
        if prefix is None:
            return False
        identity = route[len(prefix):]
        if prefix.startswith("__asset_"):
            self._v5_selected_asset_ids = (identity,)
            if prefix == "__asset_collection__:":
                self._collections_workspace.add_asset_ids_to_collection((identity,))
            elif prefix == "__asset_export__:":
                self._select_workspace("Export")
            else:
                media_type = AssetCatalogService(self._library_database_path).asset_type(identity)
                workspace_name = {
                    "photo": "Photos", "image": "Photos",
                    "sound": "Sounds",
                    "video": "Videos",
                    "document": "Documents",
                    "map": "Map",
                }.get(media_type, "Library Overview")
                self._select_workspace(workspace_name)
                target = {
                    "Photos": self._library,
                    "Sounds": self._sounds_workspace,
                    "Videos": self._videos_workspace,
                    "Documents": self._documents_workspace,
                }.get(workspace_name)
                if target is not None and hasattr(target, "select_asset"):
                    target.select_asset(identity)
            return True
        if prefix.startswith("__project_"):
            if prefix in ("__project_surveys__:", "__project_measurements__:", "__project_quality__:"):
                operations = getattr(self, "_v5_pages", {}).get("Measurements & Protocols")
                if operations is not None and hasattr(operations, "select_project"):
                    section = "Survey events" if prefix == "__project_surveys__:" else "Data quality" if prefix == "__project_quality__:" else "Samples"
                    operations.select_project(identity, section=section)
                self._select_workspace("Measurements & Protocols")
                return True
            workspace = self._science_workspaces.get("Science Projects")
            if workspace is not None and hasattr(workspace, "select_project"):
                workspace.select_project(identity, research_area=prefix == "__project_map__:")
            self._select_workspace("Science Projects")
            if prefix == "__project_map__:":
                self._select_workspace("Map")
                if self._map_workspace is not None and hasattr(self._map_workspace, "select_project"):
                    self._map_workspace.select_project(identity)
                row = None
                with sqlite3.connect(getattr(workspace, "_path")) as connection:
                    row = connection.execute("SELECT geojson FROM pm_research_areas WHERE project_id=? ORDER BY updated_at_us DESC LIMIT 1", (identity,)).fetchone()
                if row:
                    try:
                        geometry = json.loads(row[0]); geometry = geometry.get("geometry", geometry)
                        points = geometry.get("coordinates", [[]])[0]
                        if points:
                            latitude = sum(float(point[1]) for point in points) / len(points)
                            longitude = sum(float(point[0]) for point in points) / len(points)
                            if self._map_workspace is not None and hasattr(self._map_workspace, "_set_viewport_center"):
                                self._map_workspace._set_viewport_center(latitude, longitude)
                    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
                        pass
            return True
        with sqlite3.connect(self._library_database_path) as connection:
            row = connection.execute(
                """SELECT a.public_id,t.public_id,l.latitude,l.longitude,a.media_type
                   FROM observations o JOIN assets a ON a.id=o.asset_id
                   LEFT JOIN taxa t ON t.id=o.taxon_id
                   LEFT JOIN asset_locations al ON al.asset_id=a.id AND al.role='capture'
                   LEFT JOIN locations l ON l.id=al.location_id WHERE o.public_id=?""",
                (identity,),
            ).fetchone()
        if row is None:
            QMessageBox.warning(self, "Observation", "The selected observation is no longer available.")
            return True
        self._v5_selected_asset_ids = (str(row[0]),)
        if prefix == "__observation_map__:":
            self._select_workspace("Map")
            if row[2] is not None and row[3] is not None and self._map_workspace is not None:
                self._map_workspace._set_viewport_center(float(row[2]), float(row[3]))
        elif prefix == "__observation_record__:":
            self._select_workspace("Observation History")
            if row[1]: self._observation_workspace.show_taxon(str(row[1]))
        else:
            self._select_workspace({"photo":"Photos","sound":"Sounds","video":"Videos","document":"Documents"}.get(str(row[4]), "Library Overview"))
        return True

    def _workspace_changed(self, row: int) -> None:
        """Backward-compatible row routing used by older release tests."""
        if 0 <= row < len(self.WORKSPACES):
            self._select_workspace(self.WORKSPACES[row])

    @Slot()
    def _refresh_library_type_navigation(self) -> None:
        """Apply Library Types settings to navigation without removing retained data."""
        capability_to_workspace = {
            "library.photos": "Photos",
            "library.sounds": "Sounds",
            "library.videos": "Videos",
            "library.documents": "Documents",
        }
        try:
            capabilities = self._library_types_workspace._service.list()
        except Exception:
            return
        enabled_workspaces: list[str] = []
        media_workspaces = {
            "library.sounds": self._sounds_workspace,
            "library.videos": self._videos_workspace,
            "library.documents": self._documents_workspace,
        }
        for capability in capabilities:
            workspace_name = capability_to_workspace.get(capability.capability_id)
            if workspace_name is None:
                continue
            item = self._navigation_items.get(workspace_name)
            if item is not None:
                item.setHidden(not capability.enabled)
            media_workspace = media_workspaces.get(capability.capability_id)
            if media_workspace is not None:
                media_workspace.set_workspace_enabled(capability.enabled)
            elif capability.capability_id == "library.photos":
                self._library.set_workspace_enabled(capability.enabled)
                self._ai_review_workspace.set_workspace_enabled(capability.enabled)
            self._knowledge_base_workspace.set_library_capability_enabled(
                capability.capability_id, capability.enabled
            )
            if capability.enabled:
                enabled_workspaces.append(workspace_name)
        science_service = self._library_types_workspace._science_service
        if science_service is not None:
            science_to_workspace = {
                "science.projects": "Science Projects",
                "science.dossiers": "Science Dossiers",
                "science.animals": "Animal Records",
                "science.plants": "Plant & Flower Records",
                "science.marine": "Marine & Freshwater Science",
                "science.maritime": "Maritime Operations",
                "science.other_artifacts": "Other Science Artifacts",
                "science.whiteboard": "Science Whiteboard",
                "science.calendar": "Science Calendar",
                "workspace.operations": "Asset & Equipment Operations",
                "workspace.measurements": "Measurements & Protocols",
                "workspace.ai_chat": "AI Chat & MCP",
                "workspace.ai_admin": "AI Platform Administration",
                "workspace.governance": "Administration Governance",
                "workspace.reference_data": "Research Reference Data",
                "workspace.platform_parity": "Platform Parity",
            }
            for capability in science_service.list():
                workspace_name = science_to_workspace.get(capability.capability_id)
                item = self._navigation_items.get(workspace_name or "")
                if item is not None:
                    item.setHidden(not capability.enabled)
                if capability.enabled and workspace_name:
                    enabled_workspaces.append(workspace_name)
        self._refresh_navigation_branch_visibility()
        current = self._navigation.currentItem()
        if current is not None and current.isHidden():
            self._select_workspace(enabled_workspaces[0] if enabled_workspaces else "Library Types")

    def _refresh_navigation_branch_visibility(self) -> None:
        """Hide empty category branches while keeping the two navigation roots stable."""

        def update(branch: QTreeWidgetItem) -> bool:
            visible_child = False
            for index in range(branch.childCount()):
                child = branch.child(index)
                if child.childCount():
                    child.setHidden(not update(child))
                if not child.isHidden():
                    visible_child = True
            return visible_child

        for index in range(self._navigation.topLevelItemCount()):
            update(self._navigation.topLevelItem(index))

    @Slot()
    def reset_workspace_layout(self) -> None:
        self._navigation_dock.setFloating(False)
        self._inspector_dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._navigation_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._inspector_dock)
        self._navigation_dock.setVisible(True)
        self._inspector_dock.setVisible(True)
        self._navigation_dock.raise_()
        self._inspector_dock.raise_()

    @Slot()
    def back_up_library(self) -> None:
        self._default_backup_directory.mkdir(parents=True, exist_ok=True)
        suggested = self._default_backup_directory / suggested_backup_name(self._library_name)
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Back Up Aperture Library",
            str(suggested),
            "Aperture database backup (*.sqlite3);;SQLite database (*.db)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.exists():
            QMessageBox.warning(
                self,
                "Backup not created",
                "Aperture never overwrites an existing backup. Choose a new file name.",
            )
            return
        labels = [
            "Catalog only",
            "Catalog + Aperture originals",
            "Catalog + linked-original manifest",
            "Complete storage-aware backup",
        ]
        label, accepted = QInputDialog.getItem(
            self, "Backup contents", "Include", labels, 0, False
        )
        if not accepted:
            return
        scope = {
            labels[0]: BackupScope.CATALOG_ONLY,
            labels[1]: BackupScope.CATALOG_AND_MANAGED_ORIGINALS,
            labels[2]: BackupScope.CATALOG_AND_REFERENCE_MANIFEST,
            labels[3]: BackupScope.COMPLETE,
        }[label]
        self._backup_action.setEnabled(False)
        self.statusBar().showMessage("Backup queued in Activity Center…", 10000)

        def operation(progress, cancelled):
            progress(0, 3, "Creating catalog snapshot…")
            if cancelled():
                raise InterruptedError("Backup cancelled")
            result = self._backup_service.create(destination, scope=scope)
            progress(2, 3, "Verifying backup manifest and checksum…")
            if cancelled():
                raise InterruptedError("Backup cancelled after safe checkpoint")
            progress(3, 3, "Backup complete")
            size_mib = result.size_bytes / (1024 * 1024)
            return (
                "The selected library content was backed up and verified.\n"
                f"Backup: {result.database_path}\n"
                f"Manifest: {result.manifest_path}\n"
                f"Size: {size_mib:.1f} MiB\n"
                f"SHA-256: {result.sha256}\n"
                f"Scope: {result.scope.value}\n"
                f"Managed originals copied: {result.managed_files_copied}\n"
                f"Linked originals listed: {result.referenced_files_listed}"
            )

        self._activity_center.start(
            "Back up Aperture Library",
            str(destination),
            operation,
            kind="backup.library",
            payload={"destination": str(destination), "scope": scope.value},
        )
        self._backup_action.setEnabled(True)
        self.open_activity_center()

    def _select_backup_file(self, title: str) -> Path | None:
        self._default_backup_directory.mkdir(parents=True, exist_ok=True)
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            title,
            str(self._default_backup_directory),
            "Aperture database backup (*.sqlite3 *.db)",
        )
        return Path(selected) if selected else None

    @Slot()
    def verify_backup(self) -> None:
        selected = self._select_backup_file("Verify Aperture Backup")
        if selected is None:
            return
        try:
            verified = self._recovery_service.verify(selected)
        except Exception as exc:
            QMessageBox.critical(
                self, "Backup verification failed", f"The selected backup is not valid.\n\n{exc}"
            )
            return
        QMessageBox.information(
            self,
            "Backup verified",
            "The backup and checksum manifest are valid.\n\n"
            f"Library: {verified.library_name}\nCreated: {verified.created_at_utc}\n"
            f"Size: {verified.size_bytes / (1024 * 1024):.1f} MiB\nSHA-256: {verified.sha256}",
        )

    @Slot()
    def manage_backups(self) -> None:
        """Open the dedicated manager where backups can be verified, restored, or deleted."""
        self.restore_library()

    @Slot()
    def show_update_history(self) -> None:
        entries = self._update_history_store.load(self._update_history_path)
        if not entries:
            QMessageBox.information(
                self,
                "Update History",
                "No completed update attempts have been recorded for this library.",
            )
            return
        summary = "\n\n".join(
            f"{entry.created_at_utc} — Aperture {entry.version} — {entry.status}\n{entry.detail}".rstrip()
            for entry in entries
        )
        QMessageBox.information(self, "Update History", summary[:12000])

    @Slot()
    def restore_library(self) -> None:
        """Open the standalone Maintenance Center and verify its first visible window."""
        import subprocess
        import time
        import uuid

        log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aperture" / "Logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        # Do not create a temporary placeholder here: an open descriptor blocks deletion on Windows.
        # Windows cannot unlink that placeholder.  A unique path is enough because
        # the Maintenance Center creates the acknowledgement atomically.
        ready_path = log_dir / f"maintenance-ready-{uuid.uuid4().hex}.json"
        for stale in log_dir.glob("maintenance-ready-*.json*"):
            with contextlib.suppress(OSError):
                stale.unlink(missing_ok=True)

        python = Path(os.sys.executable).resolve()
        direct_entry = False
        if os.name == "nt":
            packaged = Path(os.sys.prefix) / "Aperture Maintenance Center.exe"
            console_script = Path(os.sys.prefix) / "Scripts" / "aperture-maintenance-center.exe"
            pythonw = Path(os.sys.prefix) / "pythonw.exe"
            if packaged.is_file():
                python = packaged
                direct_entry = True
            elif console_script.is_file():
                python = console_script
                direct_entry = True
            elif pythonw.is_file():
                python = pythonw
        common_args = [
            "--library", str(self._session_path.parent),
            "--ready-file", str(ready_path),
            "--intent", "restore",
        ]
        if direct_entry:
            command = [str(python), *common_args]
        else:
            command = [
                str(python), "-m", "natureai_next.bootstrap.maintenance_center", *common_args
            ]

        launch_log = log_dir / "maintenance-launch.jsonl"

        def record(status: str, detail: str = "") -> None:
            import json
            from datetime import datetime

            payload = {
                "created_at_utc": datetime.now(UTC).isoformat(),
                "status": status,
                "detail": detail,
                "command": command,
            }
            with launch_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

        record("launch-requested")
        kwargs: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        try:
            process = subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]
        except OSError as exc:
            record("launch-failed", str(exc))
            QMessageBox.critical(
                self,
                "Maintenance Center unavailable",
                f"Aperture could not start the Maintenance Center.\n\n{exc}",
            )
            return

        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if ready_path.is_file():
                record("window-ready")
                ready_path.unlink(missing_ok=True)
                self.statusBar().showMessage("Aperture Maintenance Center opened", 10000)
                return
            if process.poll() is not None:
                record("process-exited", f"exit code {process.returncode}")
                QMessageBox.critical(
                    self,
                    "Maintenance Center unavailable",
                    "The Maintenance Center stopped before its window appeared. "
                    "See maintenance-launch.jsonl and maintenance-bootstrap.jsonl in the Aperture log folder.",
                )
                return
            time.sleep(0.05)

        record("window-timeout")
        QMessageBox.critical(
            self,
            "Maintenance Center unavailable",
            "The Maintenance Center started but did not display a window within 12 seconds. "
            "Aperture remains open. See maintenance-launch.jsonl and maintenance-bootstrap.jsonl in the Aperture log folder.",
        )

    @Slot()
    def check_for_updates(self) -> None:
        settings = self._update_settings_store.load(self._update_settings_path)
        current = str(settings.source) if settings.source else ""
        selected = QFileDialog.getExistingDirectory(
            self, "Select Aperture update location", current
        )
        if not selected:
            return
        settings = UpdateSettings(
            source=Path(selected),
            check_at_startup=settings.check_at_startup,
            channel=settings.channel,
        )
        self._update_settings_store.save(self._update_settings_path, settings)
        self.statusBar().showMessage("Checking configured update location…")
        try:
            candidate = self._update_service.check(settings.source, channel=settings.channel)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Update check failed",
                f"Aperture could not check the update location.\n\n{exc}",
            )
            self.statusBar().showMessage("Update check failed", 15000)
            return
        if candidate is None:
            QMessageBox.information(
                self,
                "Aperture is up to date",
                "No newer compatible Stable update was found in the configured location.",
            )
            self.statusBar().showMessage("No update available", 10000)
            return
        if self._activity_center.running_count or self._ai_review_workspace.generation_busy:
            QMessageBox.information(
                self,
                "Finish background work first",
                "Aperture cannot install an update while background work is active. "
                "Wait for it to finish or cancel it, then check for updates again.",
            )
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle(f"Aperture {candidate.version} is available")
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setText(candidate.release_notes[:3000])
        prompt.setInformativeText(
            "Choose whether to create a verified library backup before installing. "
            "Aperture will stage the update, start the updater, close, install, and restart automatically."
        )
        backup_button = prompt.addButton("Back Up and Install", QMessageBox.ButtonRole.AcceptRole)
        no_backup_button = prompt.addButton(
            "Install Without Backup", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(backup_button)
        prompt.exec()
        clicked = prompt.clickedButton()
        if clicked is cancel_button or clicked not in {backup_button, no_backup_button}:
            return
        create_backup = clicked is backup_button
        backup = None
        try:
            if create_backup:
                self._default_backup_directory.mkdir(parents=True, exist_ok=True)
                backup = self._backup_service.create(
                    self._default_backup_directory / suggested_backup_name(self._library_name)
                )
            staged = self._update_service.stage(candidate, self._update_staging_directory)
            augment_request(
                staged.request_path, parent_pid=os.getpid(), library_path=self._session_path.parent
            )
            helper = launch_helper(
                HelperLaunch(
                    module="natureai_next.bootstrap.native_updater",
                    request_path=staged.request_path,
                    parent_pid=os.getpid(),
                    library_path=self._session_path.parent,
                )
            )
            wait_for_helper_ready(helper, staged.request_path, timeout_seconds=10.0)
        except Exception as exc:
            QMessageBox.critical(
                self, "Update not started", f"Aperture did not start the update.\n\n{exc}"
            )
            self.statusBar().showMessage("Update start failed", 15000)
            return
        backup_text = f"\n\nBackup: {backup.database_path}" if backup is not None else ""
        QMessageBox.information(
            self,
            "Restarting to install",
            f"Aperture {candidate.version} is staged and the updater has started."
            f"{backup_text}\n\nAperture will now close, install the update, and restart automatically.",
        )
        self.statusBar().showMessage(f"Restarting to install Aperture {candidate.version}…")
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)
        else:
            QTimer.singleShot(0, self.close)

    def open_import_folder(self) -> None:
        self._select_workspace("Imports")
        self._imports.choose_folder()

    def _on_import_finished(self, summary: object) -> None:
        imported = int(getattr(summary, "imported", 0))
        failed = int(getattr(summary, "failed", 0))
        results = tuple(getattr(summary, "results", ()))
        imported_results = tuple(
            result
            for result in results
            if getattr(result, "asset_public_id", None)
            and str(getattr(result, "state", "")) in {"imported", "attached"}
        )
        photo_ids = []
        imported_kinds: set[ImportSourceKind] = set()
        for result in imported_results:
            source_path = getattr(result, "source_path", None)
            kind = classify_import_source(Path(str(source_path))) if source_path else None
            if kind is not None:
                imported_kinds.add(kind)
            if kind in {ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO}:
                photo_ids.append(str(result.asset_public_id))
        self.statusBar().showMessage(
            f"Import completed • {imported} imported • {failed} failed", 15000
        )
        self._sounds_workspace.refresh()
        self._videos_workspace.refresh()
        self._documents_workspace.refresh()
        self._library.show_imported(tuple(photo_ids), imported=len(photo_ids), failed=failed)
        if photo_ids:
            self._select_workspace("Photos")
        elif ImportSourceKind.SOUND in imported_kinds:
            self._select_workspace("Sounds")
        elif ImportSourceKind.VIDEO in imported_kinds:
            self._select_workspace("Videos")
        elif ImportSourceKind.DOCUMENT in imported_kinds:
            self._select_workspace("Documents")

    @Slot(object, str)
    def _open_viewer(self, ordered_ids: tuple[str, ...], public_id: str) -> None:
        viewer = ViewerDialog(
            ordered_ids=ordered_ids,
            public_id=public_id,
            catalog=self._catalog_service,
            previews=self._thumbnail_service,
            parent=self,
            enrichment_controller=self._enrichment_controller,
        )
        self._viewers.add(viewer)
        viewer.destroyed.connect(lambda _object=None, dialog=viewer: self._viewers.discard(dialog))
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    @Slot()
    def open_activity_center(self) -> None:
        self._select_workspace("Activity Center")
        self._navigation_dock.setVisible(True)
        self._navigation_dock.raise_()

    @Slot(object)
    def open_observation_history(self, taxon_public_id: object = None) -> None:
        self._observation_workspace.refresh()
        if isinstance(taxon_public_id, str) and taxon_public_id:
            self._observation_workspace.show_taxon(taxon_public_id)
        self._select_workspace("Observation History")
        self._navigation_dock.setVisible(True)
        self._navigation_dock.raise_()

    @Slot()
    def open_ecology(self) -> None:
        self._select_workspace("Conservation & Seasonality")

    def open_observation_statistics(self) -> None:
        self._observation_statistics_workspace.refresh()
        self._select_workspace("Life Lists & Statistics")
        self._navigation_dock.setVisible(True)
        self._navigation_dock.raise_()

    @Slot()
    def open_ai_resources(self) -> None:
        self._ai_resources_workspace.refresh()
        self._select_workspace("AI Resources")

    @Slot()
    def open_regional_knowledge(self) -> None:
        self._regional_workspace.refresh()
        self._select_workspace("Regional Knowledge")

    @Slot()
    def open_health_check(self) -> None:
        self._health_workspace.refresh()
        self._select_workspace("Health Check")

    @Slot(object)
    def _apply_branding(self, branding: object) -> None:
        self._branding = branding
        self.setWindowTitle(f"{branding.application_name} — {self._library_name}")
        self._about_action.setText(f"About {branding.application_name}…")
        QApplication.instance().setApplicationName(branding.application_name)

    @Slot()
    def open_about(self) -> None:
        self._about_dialog_factory().exec()

    @Slot()
    def open_diagnostics(self) -> None:
        self._diagnostics_workspace.refresh()
        self._select_workspace("Diagnostics")

    @Slot()
    def _activity_status_changed(self) -> None:
        running = self._activity_center.running_count
        failed = sum(
            1 for item in self._activity_center.records if item.state in {"failed", "interrupted"}
        )
        if running:
            label = f"Operations Center ({running} running)"
        elif failed:
            label = f"Operations Center ({failed} attention)"
        else:
            label = "Operations Center"
        self._activity_button.setText(label)
        self.WORKSPACES.index("Activity Center")
        nav_label = "Operations Center"
        if running:
            nav_label += f" ({running})"
        elif failed:
            nav_label += f" (!{failed})"
        item = self._navigation_items.get("Activity Center")
        if item is not None:
            item.setText(0, nav_label)
        self._activity_button.setVisible(bool(self._activity_center.records))
        if self._exit_after_tasks and running == 0:
            self._exit_after_tasks = False
            QTimer.singleShot(0, self.close)

    def _create_required_shutdown_backup(self) -> bool:
        marker = self._library_database_path.parent / "backup-required.json"
        if not marker.is_file():
            return True
        self._default_backup_directory.mkdir(parents=True, exist_ok=True)
        destination = self._default_backup_directory / suggested_backup_name(self._library_name)
        counter = 1
        while destination.exists():
            destination = destination.with_name(f"{destination.stem}-{counter}{destination.suffix}")
            counter += 1
        self.statusBar().showMessage(
            "Finalizing taxonomy update and creating a verified recovery backup…"
        )
        try:
            result = self._backup_service.create(destination)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Required backup failed",
                "Aperture installed the taxonomy successfully, but could not create the required "
                f"shutdown backup. The backup will be retried on the next shutdown.\n\n{exc}",
            )
            return False
        with contextlib.suppress(OSError):
            marker.unlink()
        self.statusBar().showMessage(f"Verified backup created: {result.database_path.name}", 5000)
        return True

    def _show_shutdown_progress(self) -> None:
        if getattr(self, "_shutdown_dialog", None) is not None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Shutdown")
        dialog.setModal(True)
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        title = QLabel("<h2>Shutting down…</h2>")
        self._shutdown_status = QLabel("Preparing a safe shutdown")
        self._shutdown_progress = QProgressBar()
        self._shutdown_progress.setRange(0, 6)
        self._shutdown_progress.setValue(0)
        layout.addWidget(title)
        layout.addWidget(self._shutdown_status)
        layout.addWidget(self._shutdown_progress)
        self._shutdown_dialog = dialog
        dialog.show()
        QApplication.processEvents()

    def _set_shutdown_stage(self, stage: int, text: str) -> None:
        self._show_shutdown_progress()
        self._shutdown_status.setText(text)
        self._shutdown_progress.setValue(stage)
        QApplication.processEvents()

    def closeEvent(self, event: object) -> None:
        self._set_shutdown_stage(0, "Checking active work…")
        if self._activity_center.running_count:
            message = QMessageBox(self)
            message.setWindowTitle("Background work is still running")
            message.setIcon(QMessageBox.Icon.Warning)
            message.setText("Aperture is still performing background work.")
            message.setInformativeText(
                "Closing now would interrupt the active operation. Keep Aperture running, "
                "or cancel the tasks and exit after they reach a safe checkpoint. Partial "
                "downloads and progress checkpoints will be preserved for Resume / Retry."
            )
            keep = message.addButton("Keep running", QMessageBox.ButtonRole.RejectRole)
            cancel_exit = message.addButton(
                "Cancel tasks and exit", QMessageBox.ButtonRole.DestructiveRole
            )
            message.setDefaultButton(keep)
            message.exec()
            if message.clickedButton() is cancel_exit:
                self._exit_after_tasks = True
                self._activity_center.cancel_all()
                self.statusBar().showMessage("Cancelling background tasks at a safe checkpoint…")
            if getattr(self, "_shutdown_dialog", None) is not None:
                self._shutdown_dialog.hide()
                self._shutdown_dialog = None
            event.ignore()
            return
        if self._ai_review_workspace.generation_busy:
            QMessageBox.information(
                self,
                "BioCLIP generation running",
                "Wait for the local BioCLIP generation to finish or cancel it before closing Aperture.",
            )
            if getattr(self, "_shutdown_dialog", None) is not None:
                self._shutdown_dialog.hide()
                self._shutdown_dialog = None
            event.ignore()
            return
        self._set_shutdown_stage(1, "Creating the required shutdown backup…")
        if not self._create_required_shutdown_backup():
            event.ignore()
            return
        # Lazy workspaces own short-lived query workers.  Closing the main
        # window must drain their event loops before Qt destroys the widgets;
        # otherwise Linux aborts with "QThread: Destroyed while thread is still
        # running" after an ordinary workspace visit.
        self._set_shutdown_stage(2, "Stopping background workers…")
        threads = tuple(self.findChildren(QThread))
        for thread in threads:
            thread.requestInterruption()
            thread.quit()
        unfinished = [thread for thread in threads if not thread.wait(10000)]
        if unfinished:
            self.statusBar().showMessage(
                f"Waiting for {len(unfinished)} background worker(s) to stop safely…"
            )
            event.ignore()
            QTimer.singleShot(250, self.close)
            return
        self._set_shutdown_stage(4, "Saving workspace and library state…")
        current = self._navigation.currentItem()
        current_name = (
            current.data(0, Qt.ItemDataRole.UserRole) if current is not None else "Photos"
        )
        workspace = str(current_name or "Photos").casefold().replace(" ", "_")
        state = SessionState(
            workspace=workspace,
            window_geometry_b64=bytes(self.saveGeometry().toBase64()).decode("ascii"),
            dock_state_b64=None,
            grid_thumbnail_size=self._session.grid_thumbnail_size,
            sort_mode=self._session.sort_mode,
            inspector_visible=self.findChild(QDockWidget, "inspectorDock").isVisible(),
        )
        self._store.save(self._session_path, state)
        self._set_shutdown_stage(5, "Releasing application resources…")
        super().closeEvent(event)
        # A finished startup splash can remain a hidden top-level widget on
        # some Qt Linux platform plugins.  Explicitly ending the application
        # after an accepted main-window close gives normal close identical
        # semantics on X11, Wayland, and the off-screen acceptance platform.
        app = QApplication.instance()
        if app is not None:
            self._set_shutdown_stage(6, "Shutdown complete.")
            QTimer.singleShot(0, app.quit)


def run_desktop(
    *,
    library_name: str,
    session_path: Path,
    enrichment_database_path: Path,
    import_service: ImportApplicationService,
    catalog_service: CatalogApplicationService,
    thumbnail_service: CatalogThumbnailService,
    catalog_edit_service: CatalogEditApplicationService,
    search_service: QuickSearchApplicationService,
    views_service: LibraryViewsApplicationService,
    maintenance_service: object | None = None,
    ai_review_workspace_factory: Callable[[Callable[[], tuple[str, ...]]], AIReviewWorkspace],
    backup_service: LibraryBackupService,
    default_backup_directory: Path,
    branding_store: BrandingStore,
    health_service: LibraryHealthService | None = None,
    map_workspace_factory: Callable[[], QWidget] | None = None,
    knowledge_center_workspace_factory: Callable[[], QWidget] | None = None,
    offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,
    on_about_to_quit: Callable[[], None] = lambda: None,
    argv: Sequence[str] | None = None,
    startup_timeline: StartupTimeline | None = None,
    app: QApplication | None = None,
    startup_splash: FieldoraStartupSplash | None = None,
) -> int:
    app = app or QApplication.instance() or QApplication(list(argv or []))
    from natureai_next.ui.qt.local_login import LocalLoginDialog
    profile_path = session_path.parent / "local-profiles.json"

    # The startup splash is an always-on-top window.  Keeping it visible while
    # the modal login dialog is opened places the login behind the splash on
    # Windows, making startup appear frozen at the preceding 88% milestone.
    # Hide it for authentication, then restore it while the main window is
    # constructed.
    if startup_splash is not None:
        startup_splash.hide()
        app.processEvents()

    login = LocalLoginDialog(profile_path)
    if login.exec() != QDialog.DialogCode.Accepted or not login.profile:
        if startup_splash is not None:
            startup_splash.close()
        return 0

    os.environ["FIELDORA_IDENTITY_ID"] = str(login.profile["username"])
    WorkspaceContext.current().identity_changed(source="login")
    os.environ["FIELDORA_PROFILE_ROLE"] = str(login.profile["role"])
    os.environ["FIELDORA_PROFILE_STORE"] = str(profile_path)
    if startup_splash is not None:
        startup_splash.show()
        startup_splash.raise_()
        startup_splash.set_stage("Constructing Fieldora window…", 92)
    app.setApplicationName("Fieldora")
    app.setOrganizationName("natuurgids.org")
    icon_path = Path(__file__).resolve().parents[2] / "resources" / "fieldora.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.aboutToQuit.connect(on_about_to_quit)
    window = None
    try:
        window = MainWindow(
            library_name=library_name,
            session_path=session_path,
            enrichment_database_path=enrichment_database_path,
            import_service=import_service,
            catalog_service=catalog_service,
            thumbnail_service=thumbnail_service,
            catalog_edit_service=catalog_edit_service,
            search_service=search_service,
            views_service=views_service,
            maintenance_service=maintenance_service,
            ai_review_workspace_factory=ai_review_workspace_factory,
            backup_service=backup_service,
            default_backup_directory=default_backup_directory,
            branding_store=branding_store,
            health_service=health_service,
            map_workspace_factory=map_workspace_factory,
            knowledge_center_workspace_factory=knowledge_center_workspace_factory,
            offline_map_setup_factory=offline_map_setup_factory,
        )
    except Exception:
        # MainWindow construction may have created child workers before a later
        # workspace fails. Stop every discoverable QThread synchronously before
        # unwinding so Qt never destroys a running thread.
        for thread in app.findChildren(QThread):
            try:
                thread.requestInterruption()
                thread.quit()
            except Exception:
                pass
        for thread in app.findChildren(QThread):
            with contextlib.suppress(Exception):
                thread.wait(5000)
        try:
            on_about_to_quit()
        finally:
            app.processEvents()
        raise
    window.show()
    window.bind_per_monitor_display_scaling()
    if startup_splash is not None:
        startup_splash.set_stage("Ready", 100)
        startup_splash.finish(window)
    if startup_timeline is not None:

        def record_first_paint() -> None:
            startup_timeline.mark("main-window-visible")
            startup_timeline.write(library=library_name)

        QTimer.singleShot(0, record_first_paint)
    # Platform acceptance can request a real, off-screen GUI launch that closes
    # itself after the event loop and all first-run workspaces have initialized.
    # This is deliberately opt-in and has no effect on normal users.
    smoke_seconds = os.environ.get("APERTURE_SMOKE_TEST_SECONDS")
    if smoke_seconds:
        try:
            delay_ms = max(250, int(float(smoke_seconds) * 1000))
        except ValueError as exc:
            raise ValueError("APERTURE_SMOKE_TEST_SECONDS must be numeric") from exc
        QTimer.singleShot(delay_ms, window.close)
    try:
        return app.exec()
    finally:
        # Some Linux Qt platform plugins can return from the event loop without
        # delivering aboutToQuit.  Library locks and SQLite connections must
        # still be released on every normal or exceptional event-loop exit.
        on_about_to_quit()
