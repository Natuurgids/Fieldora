"""Stable desktop launcher command-line boundary."""

from __future__ import annotations

import argparse
import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from natureai_next import __version__
from natureai_next.bootstrap.container import build_foundation_container
from natureai_next.bootstrap.startup_timing import StartupTimeline
from natureai_next.infrastructure.filesystem.branding_store import TomlBrandingStore
from natureai_next.infrastructure.filesystem.library_lock import LibraryLockedError
from natureai_next.shared.errors import NatureAIError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="natureai-next")
    parser.add_argument("--library", type=Path, help="Library to open")
    parser.add_argument("--config-root", type=Path, help="Configuration root override")
    parser.add_argument("--safe-mode", action="store_true", help="Disable third-party plugins")
    parser.add_argument("--diagnostics", action="store_true", help="Start in diagnostics mode")
    parser.add_argument(
        "--no-update-check", action="store_true", help="Disable update checks for this session"
    )
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    started_at = time.perf_counter()
    startup = StartupTimeline(started_at=started_at)
    startup.mark("process-started")
    args = build_parser().parse_args(argv)
    overrides: dict[str, object] = {}
    if args.log_level:
        overrides["application"] = {"log_level": args.log_level}
    if args.no_update_check:
        application = dict(overrides.get("application", {}))
        application["update_check_policy"] = "disabled"
        overrides["application"] = application
    try:
        container = build_foundation_container(
            config_root=args.config_root, session_overrides=overrides
        )
    except NatureAIError as exc:
        print(exc.descriptor.summary)
        return 2
    startup.mark("foundation-ready")
    logging.getLogger("natureai_next.bootstrap").info(
        "Foundation initialized",
        extra={
            "context": {
                "safe_mode": args.safe_mode,
                "diagnostics": args.diagnostics,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
        },
    )
    if args.library is None:
        print(
            f"NatureAI Next ready at {container.paths.local_root}; provide --library to open the desktop"
        )
        return 0
    from natureai_next.application.library_service import LibraryService
    from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend

    service = LibraryService(
        container.clock,
        container.uuid_generator,
        backend_factory=lambda clock, ids, settings: SqliteLibraryLifecycleBackend(
            clock, ids, settings
        ),
    )
    library_root = args.library.expanduser().resolve()
    data_root = container.paths.local_root.expanduser().resolve()
    try:
        library_root.relative_to(data_root)
        overlap = True
    except ValueError:
        try:
            data_root.relative_to(library_root)
            overlap = True
        except ValueError:
            overlap = False
    if overlap:
        print(
            f"Library and application-data directories must be separate and non-nested.\nLibrary: {library_root}\nApplication data: {data_root}"
        )
        return 4
    try:
        opened_context = service.open_or_create_clean(library_root)
    except LibraryLockedError as exc:
        owner = exc.owner
        detail = "Aperture is already open with this library."
        if owner is not None:
            detail += f"\n\nProcess ID: {owner.pid}\nComputer: {owner.host}"
        print(detail)
        return 3
    startup.mark("library-opened")
    logging.getLogger("natureai_next.bootstrap").info(
        "Library opened",
        extra={"context": {"elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1)}},
    )
    from natureai_next.ui.qt.startup_splash import create_startup_splash

    app, splash = create_startup_splash(
        version=f"Fieldora {__version__}",
        library_name=args.library.name,
    )
    startup.mark("startup-splash-visible")
    splash.set_stage("Preparing desktop services…", 24)
    with opened_context as opened:
        from natureai_next.application.ai_generation import LocalSuggestionGenerationService
        from natureai_next.application.ai_resources import LocalAIResourceService
        from natureai_next.application.ai_review import SuggestionService
        from natureai_next.application.asset_analysis import AssetAnalysisService
        from natureai_next.application.backup import LibraryBackupService
        from natureai_next.application.catalog_browsing import (
            CatalogEditService,
            CatalogQueryService,
        )
        from natureai_next.application.catalog_maintenance import CatalogMaintenanceService
        from natureai_next.application.ecology import EcologicalContextService
        from natureai_next.application.health import LibraryHealthService
        from natureai_next.application.import_service import ImportService
        from natureai_next.application.observation_intelligence import (
            ObservationIntelligenceService,
        )
        from natureai_next.application.regional import RegionalProfileService
        from natureai_next.application.regional_acquisition import (
            RegionalKnowledgeAcquisitionService,
        )
        from natureai_next.application.search import LibraryViewsService, QuickSearchService
        from natureai_next.infrastructure.ai.preprocessing import BioClipImagePreprocessor
        from natureai_next.infrastructure.database.ai import SqliteAIRepository
        from natureai_next.infrastructure.database.ai_generation import SqliteTaxonomyEmbeddingStore
        from natureai_next.infrastructure.database.ai_review import SqliteSuggestionStore
        from natureai_next.infrastructure.database.analyses import SqliteAssetAnalysisRepository
        from natureai_next.infrastructure.database.catalog_gui import SqliteCatalogGuiAdapter
        from natureai_next.infrastructure.database.ecology import SqliteEcologicalContextStore
        from natureai_next.infrastructure.database.integrity import check_integrity
        from natureai_next.infrastructure.database.observation_intelligence import (
            SqliteObservationIntelligenceAdapter,
        )
        from natureai_next.infrastructure.database.regional import SqliteRegionalProfileStore
        from natureai_next.infrastructure.database.search import (
            SqliteCollectionAdapter,
            SqliteSavedSearchAdapter,
            SqliteSearchAdapter,
        )
        from natureai_next.infrastructure.database.suggestion_generation import (
            SqliteSuggestionGenerationSource,
        )
        from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
        from natureai_next.infrastructure.filesystem.importing import (
            DirectorySourceScanner,
            ShardedManagedFileStore,
            StreamingFileFingerprinter,
            XmpSidecarResolver,
        )
        from natureai_next.infrastructure.imaging.catalog_thumbnails import (
            PillowCatalogThumbnailProvider,
        )
        from natureai_next.infrastructure.imaging.pillow_adapter import PillowImageDecoder
        from natureai_next.infrastructure.imaging.rawpy_adapter import (
            HybridImageDecoder,
            HybridMetadataReader,
            RawPyImageDecoder,
            RawPyMetadataReader,
            RawPyThumbnailRenderer,
        )
        from natureai_next.infrastructure.metadata.pillow_reader import PillowMetadataReader
        from natureai_next.infrastructure.metadata.xmp_reader import XmpMetadataReader
        from natureai_next.infrastructure.subsystems.maps import (
            OfflineMapCatalog,
            OfflineMapPackageService,
        )
        from natureai_next.ports.offline_map_setup import OfflineMapSetupPlatform
        from natureai_next.ui.presentation.ai_review import AIReviewModel
        from natureai_next.ui.qt.ai_review import AIReviewWorkspace
        from natureai_next.ui.qt.application import run_desktop

        splash.set_stage("Connecting library services…", 34)
        fingerprinter = StreamingFileFingerprinter()
        managed_store = ShardedManagedFileStore(opened.layout.managed_originals, fingerprinter)
        image_decoder = HybridImageDecoder(PillowImageDecoder(), RawPyImageDecoder())
        from natureai_next.application.derivatives import DurableDerivativeScheduler, schedule_missing_photo_thumbnails
        from natureai_next.application.jobs import JobService
        from natureai_next.infrastructure.database.job_commands import SqliteJobCommandStore
        from natureai_next.infrastructure.imaging.cache import DerivativeCache
        from natureai_next.jobs.engine import JobEngine
        from natureai_next.jobs.media_handlers import GenerateDerivativeHandler

        job_service = JobService(
            SqliteJobCommandStore(opened.connection_factory), container.clock, container.uuid_generator
        )
        derivative_scheduler = DurableDerivativeScheduler(job_service)
        derivative_cache = DerivativeCache(
            opened.layout.thumbnails, image_decoder, "natureai.hybrid.catalog.build29"
        )
        job_engine = JobEngine(
            opened.connection_factory,
            [GenerateDerivativeHandler(
                derivative_cache, factory=opened.connection_factory, library_root=opened.layout.root
            )],
            # One derivative worker protects the desktop interaction budget.
            # Throughput scales through server workers, not GUI-process threads.
            io_workers=1,
            cpu_workers=0,
            worker_id="Aperture-Build29",
        )
        job_engine.start()
        # Reconcile clean-install and interrupted imports whose derivative submission
        # was missed or failed before a valid thumbnail record was committed.
        # Reconciliation can inspect and submit thousands of records. Delay it
        # until after the desktop has become interactive and never make startup
        # or navigation wait for it.
        thumbnail_reconcile = threading.Timer(
            15.0,
            schedule_missing_photo_thumbnails,
            args=(opened.connection_factory, derivative_scheduler),
        )
        thumbnail_reconcile.name = "fieldora-thumbnail-reconcile"
        thumbnail_reconcile.daemon = True
        thumbnail_reconcile.start()
        import_service = ImportService(
            uow_factory=lambda: SqliteUnitOfWork(opened.connection_factory),
            scanner=DirectorySourceScanner(),
            fingerprinter=fingerprinter,
            managed_store=managed_store,
            decoder=image_decoder,
            metadata_reader=HybridMetadataReader(PillowMetadataReader(), RawPyMetadataReader()),
            clock=container.clock,
            ids=container.uuid_generator,
            sidecar_resolver=XmpSidecarResolver(),
            sidecar_store=ShardedManagedFileStore(opened.layout.sidecars, fingerprinter),
            sidecar_metadata_reader=XmpMetadataReader(),
            derivative_scheduler=derivative_scheduler,
        )
        splash.set_stage("Loading catalog and collections…", 46)
        catalog_adapter = SqliteCatalogGuiAdapter(opened.connection_factory)
        catalog_service = CatalogQueryService(catalog_adapter)
        catalog_edit_service = CatalogEditService(catalog_adapter, container.clock)
        search_adapter = SqliteSearchAdapter(opened.connection_factory)
        search_service = QuickSearchService(search_adapter)
        views_service = LibraryViewsService(
            saved=SqliteSavedSearchAdapter(opened.connection_factory),
            collections=SqliteCollectionAdapter(opened.connection_factory),
            search=search_adapter,
            clock=container.clock,
            ids=container.uuid_generator,
        )
        thumbnail_service = PillowCatalogThumbnailProvider(
            thumbnail_root=opened.layout.thumbnails,
            preview_root=opened.layout.previews,
            library_root=opened.layout.root,
            raw_renderer=RawPyThumbnailRenderer(),
        )
        maintenance_service = CatalogMaintenanceService(
            uow_factory=lambda: SqliteUnitOfWork(opened.connection_factory),
            fingerprinter=fingerprinter,
            managed_store=managed_store,
            clock=container.clock,
            ids=container.uuid_generator,
            cache_roots=(opened.layout.thumbnails, opened.layout.previews, opened.layout.root),
            read_connection_factory=lambda: opened.connection_factory.connect(read_only=True),
        )
        splash.set_stage("Connecting modular resources…", 58)
        suggestion_service = SuggestionService(SqliteSuggestionStore(opened.connection_factory))
        observation_intelligence_service = ObservationIntelligenceService(
            SqliteObservationIntelligenceAdapter(opened.connection_factory)
        )
        from natureai_next.application.knowledge_engine import KnowledgeEngine

        desktop_knowledge_engine = KnowledgeEngine(
            observations=observation_intelligence_service,
            analyses=SqliteAssetAnalysisRepository(opened.connection_factory),
        )
        ecology_service = EcologicalContextService(
            SqliteEcologicalContextStore(opened.connection_factory),
            now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
        )
        from natureai_next.infrastructure.ai.package_builder import Ed25519ModelPackageBuilder
        from natureai_next.infrastructure.ai.resources import LocalAIResourceBackend
        from natureai_next.infrastructure.taxonomy.package_builder import (
            Ed25519TaxonomyPackageBuilder,
        )

        resource_service = LocalAIResourceService(
            backend=LocalAIResourceBackend(
                factory=opened.connection_factory,
                models_root=container.paths.models_dir,
                id_factory=lambda: str(container.uuid_generator.new_uuid()),
                now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
            ),
            model_package_builder=Ed25519ModelPackageBuilder(),
            taxonomy_package_builder=Ed25519TaxonomyPackageBuilder(),
        )
        from natureai_next.infrastructure.ai.engine_state import (
            ensure_aperture_bridge,
            read_engine_state,
        )

        natureai_state = read_engine_state(
            container.paths.subsystem_databases_dir / "natureai.sqlite"
        )
        if natureai_state is not None and natureai_state.ready:
            ensure_aperture_bridge(opened.connection_factory, natureai_state)
        regional_service = RegionalProfileService(
            SqliteRegionalProfileStore(opened.connection_factory),
            now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
        )
        regional_workspace = (
            Path("D:/NatureAI-Models")
            if Path("D:/NatureAI-Models").exists()
            else container.paths.models_dir.parent
        )
        from natureai_next.infrastructure.taxonomy.package_builder import (
            Ed25519TaxonomyPackageBuilder,
        )

        def install_regional_reference_taxonomy(package_path: Path, trusted_keys_path: Path) -> str:
            from natureai_next.application.ai_resources import load_trusted_key_file
            from natureai_next.application.reference_taxonomy import (
                AuthoritativeTaxonomyImportService,
            )
            from natureai_next.infrastructure.subsystems.taxonomy import (
                TAXONOMY_SUBSYSTEM_KEY,
                TaxonomyReferenceCatalog,
            )
            from natureai_next.infrastructure.taxonomy.package import Ed25519TaxonomyPackageVerifier

            taxonomy_factory = container.subsystem_registry.activate(TAXONOMY_SUBSYSTEM_KEY)
            service = AuthoritativeTaxonomyImportService(
                Ed25519TaxonomyPackageVerifier(load_trusted_key_file(trusted_keys_path)),
                TaxonomyReferenceCatalog(taxonomy_factory),
            )
            return service.install(
                package_path,
                installed_at_us=int(container.clock.now_utc().timestamp() * 1_000_000),
                source_url="https://www.gbif.org/",
            )

        regional_acquisition_service = RegionalKnowledgeAcquisitionService(
            resource_service,
            workspace=regional_workspace,
            package_builder=Ed25519TaxonomyPackageBuilder(),
            reference_installer=install_regional_reference_taxonomy,
        )
        generation_model_manager = __import__(
            "natureai_next.infrastructure.ai.dynamic_model_manager",
            fromlist=["DynamicModelManager"],
        ).DynamicModelManager(
            __import__(
                "natureai_next.infrastructure.ai.model_catalog",
                fromlist=["ModelCatalog"],
            ).ModelCatalog.load(Path(__file__).resolve().parents[1] / "resources" / "models.json"),
            container.paths.models_dir / "runtime",
        )
        generation_provider = __import__(
            "natureai_next.infrastructure.ai.catalog_provider",
            fromlist=["CatalogAIExecutionProvider"],
        ).CatalogAIExecutionProvider(generation_model_manager)
        generation_service = LocalSuggestionGenerationService(
            source=SqliteSuggestionGenerationSource(
                opened.connection_factory, generation_model_manager
            ),
            ai_repository=SqliteAIRepository(opened.connection_factory),
            taxonomy_embeddings=SqliteTaxonomyEmbeddingStore(opened.connection_factory),
            suggestions=suggestion_service,
            id_factory=lambda: str(container.uuid_generator.new_uuid()),
            now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
            provider=generation_provider,
            preprocessor_factory=lambda size, identity: BioClipImagePreprocessor(size, identity),
            analyses=AssetAnalysisService(SqliteAssetAnalysisRepository(opened.connection_factory)),
            inference_snapshot_root=opened.layout.root / "cache" / "ai-inputs",
            canonical_translation=__import__(
                "natureai_next.application.capability_translation",
                fromlist=["CapabilityTranslationService"],
            ).CapabilityTranslationService(
                opened.connection_factory.database_path,
                id_factory=lambda: str(container.uuid_generator.new_uuid()),
                clock_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
            ),
        )

        def map_workspace_factory():
            from natureai_next.application.knowledge_engine import KnowledgeEngine
            from natureai_next.application.map_workspace import OfflineMapWorkspaceService
            from natureai_next.application.temporal_map import TemporalMapService
            from natureai_next.infrastructure.database.spatial_intelligence import (
                SqliteSpatialIntelligenceAdapter,
            )
            from natureai_next.infrastructure.gpx_tracks import GpxTrackLoader
            from natureai_next.infrastructure.subsystems.map_workspace import SqliteOfflineMapQuery
            from natureai_next.infrastructure.subsystems.maps import MAPS_SUBSYSTEM_KEY
            from natureai_next.infrastructure.subsystems.vector_renderer import (
                QtWebEngineVectorRendererProbe,
            )
            from natureai_next.ui.qt.maps import OfflineMapWorkspace

            map_factory = container.subsystem_registry.activate(MAPS_SUBSYSTEM_KEY)
            knowledge_engine = KnowledgeEngine(
                spatial=SqliteSpatialIntelligenceAdapter(opened.connection_factory)
            )
            from natureai_next.bootstrap.map_renderer import create_map_web_profile
            from natureai_next.ui.qt.vector_map_view import create_vector_map_view

            profile_bundle = None

            def vector_view_factory(package, parent):
                nonlocal profile_bundle
                if profile_bundle is None:
                    profile_bundle = create_map_web_profile(map_factory, parent)
                return create_vector_map_view(profile_bundle.profile, package, parent)

            return OfflineMapWorkspace(
                lambda: OfflineMapWorkspaceService(
                    maps=SqliteOfflineMapQuery(
                        map_factory, QtWebEngineVectorRendererProbe(archive_bridge_available=True)
                    ),
                    spatial=SqliteSpatialIntelligenceAdapter(opened.connection_factory),
                    knowledge_engine=knowledge_engine,
                ),
                lambda: TemporalMapService(
                    SqliteSpatialIntelligenceAdapter(opened.connection_factory)
                ),
                vector_view_factory,
                GpxTrackLoader(),
                project_database_path=(
                    container.paths.subsystem_databases_dir / "science.sqlite3"
                ),
            )

        def knowledge_center_workspace_factory():
            from natureai_next.application.knowledge_center import KnowledgeCenterService
            from natureai_next.application.knowledge_engine import KnowledgeEngine
            from natureai_next.infrastructure.subsystems.taxonomy import (
                TAXONOMY_SUBSYSTEM_KEY,
                TaxonomyReferenceCatalog,
            )
            from natureai_next.ui.qt.knowledge_center import KnowledgeCenterWorkspace

            state: dict[str, object] = {}

            def service_factory() -> KnowledgeCenterService:
                service = state.get("service")
                if isinstance(service, KnowledgeCenterService):
                    return service
                taxonomy_factory = container.subsystem_registry.activate(TAXONOMY_SUBSYSTEM_KEY)
                catalog = TaxonomyReferenceCatalog(taxonomy_factory)
                service = KnowledgeCenterService(
                    catalog,
                    observation_intelligence_service,
                    library_public_id=opened.manifest.public_id,
                    links=catalog,
                )
                state["catalog"] = catalog
                state["service"] = service
                return service

            def knowledge_engine_factory() -> KnowledgeEngine:
                engine = state.get("engine")
                if isinstance(engine, KnowledgeEngine):
                    return engine
                service_factory()
                catalog = state["catalog"]
                engine = KnowledgeEngine(
                    taxonomy=catalog, observations=observation_intelligence_service
                )
                state["engine"] = engine
                return engine

            return KnowledgeCenterWorkspace(service_factory, knowledge_engine_factory)

        def ai_review_workspace_factory(
            selected_asset_ids: object = lambda: (),
        ) -> AIReviewWorkspace:
            if not callable(selected_asset_ids):
                raise TypeError("selected asset provider must be callable")
            return AIReviewWorkspace(
                model=AIReviewModel(suggestion_service),
                service=suggestion_service,
                action_id_factory=lambda: str(container.uuid_generator.new_uuid()),
                now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
                generation_service=generation_service,
                selected_asset_ids=selected_asset_ids,
                resource_service=resource_service,
                regional_service=regional_service,
                regional_acquisition_service=regional_acquisition_service,
                observation_service=observation_intelligence_service,
                knowledge_engine=desktop_knowledge_engine,
                ecology_service=ecology_service,
                thumbnail_service=thumbnail_service,
            )

        session_path = opened.layout.root / "session.json"
        offline_map_platform = OfflineMapSetupPlatform(
            foundation_factory=lambda: container,
            map_catalog_factory=OfflineMapCatalog,
            map_package_service_factory=OfflineMapPackageService,
            vector_map_converter_factory=lambda: __import__(
                "natureai_next.bootstrap.map_converter",
                fromlist=["create_packaged_tilemaker_converter"],
            ).create_packaged_tilemaker_converter(),
        )

        def offline_map_setup_factory(parent):
            from natureai_next.ui.qt.maintenance_center import OfflineMapPackageDialog

            return OfflineMapPackageDialog(parent, platform=offline_map_platform)

        splash.set_stage("Building active workspace…", 76)
        from natureai_next.infrastructure.subsystems.science import SCIENCE_SUBSYSTEM_KEY
        from natureai_next.infrastructure.subsystems.access_control import (
            ACCESS_CONTROL_SUBSYSTEM_KEY,
        )

        container.subsystem_registry.activate(SCIENCE_SUBSYSTEM_KEY)
        container.subsystem_registry.activate(ACCESS_CONTROL_SUBSYSTEM_KEY)
        startup.mark("desktop-services-composed")
        logging.getLogger("natureai_next.bootstrap").info(
            "Desktop services composed",
            extra={"context": {"elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1)}},
        )
        from natureai_next.bootstrap.map_renderer import prepare_map_archive_scheme

        prepare_map_archive_scheme()
        # Validate once more without mutation immediately before Qt ownership begins.
        opened.ensure_runtime_schema()
        startup.mark("runtime-schema-verified")
        logging.getLogger("natureai_next.bootstrap").info(
            "Runtime schema verified",
            extra={
                "context": {
                    "database": str(opened.connection_factory.database_path),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
                }
            },
        )
        splash.set_stage("Restoring workspace…", 88)
        try:
            return run_desktop(
                library_name=opened.manifest.display_name,
                session_path=session_path,
                enrichment_database_path=container.paths.subsystem_databases_dir / "enrichment.sqlite3",
                import_service=import_service,
                catalog_service=catalog_service,
                thumbnail_service=thumbnail_service,
                catalog_edit_service=catalog_edit_service,
                search_service=search_service,
                views_service=views_service,
                maintenance_service=maintenance_service,
                ai_review_workspace_factory=ai_review_workspace_factory,
                backup_service=LibraryBackupService(
                    opened.backup_database,
                    library_name=opened.manifest.display_name,
                    additional_databases={
                        "science": container.paths.subsystem_databases_dir
                        / "science.sqlite3",
                        "marine-maritime": container.paths.subsystem_databases_dir
                        / "marine-maritime.sqlite3",
                        "deletion-approvals": container.paths.subsystem_databases_dir
                        / "deletion-approvals.sqlite3",
                        "access-control": container.paths.subsystem_databases_dir
                        / "access-control.sqlite3",
                        "server-media": container.paths.subsystem_databases_dir
                        / "server-media.sqlite3",
                        "server-jobs": container.paths.subsystem_databases_dir
                        / "server-jobs.sqlite3",
                        "server-exports": container.paths.subsystem_databases_dir
                        / "server-exports.sqlite3",
                    },
                ),
                default_backup_directory=opened.layout.backups,
                branding_store=TomlBrandingStore(),
                map_workspace_factory=map_workspace_factory,
                knowledge_center_workspace_factory=knowledge_center_workspace_factory,
                offline_map_setup_factory=offline_map_setup_factory,
                health_service=LibraryHealthService(
                    layout=opened.layout,
                    connection_factory=opened.connection_factory,
                    integrity_checker=lambda factory, full: check_integrity(factory, full=full),
                    update_settings_path=session_path.parent / "update-settings.json",
                    subsystem_registry=container.subsystem_registry,
                ),
                on_about_to_quit=opened.close,
                startup_timeline=startup,
                app=app,
                startup_splash=splash,
            )
        finally:
            job_engine.stop(timeout=15.0)
            thumbnail_service.close()
