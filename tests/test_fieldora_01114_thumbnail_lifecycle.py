from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from natureai_next.application.derivatives import DerivativeRequest, DurableDerivativeScheduler, schedule_missing_photo_thumbnails
from natureai_next.application.jobs import JobService
from natureai_next.application.library_service import LibraryService
from natureai_next.domain.jobs import ResourceClass
from natureai_next.infrastructure.database.catalog_gui import SqliteCatalogGuiAdapter
from natureai_next.infrastructure.database.job_commands import SqliteJobCommandStore
from natureai_next.infrastructure.diagnostics.system_services import SystemClock, SystemUuidGenerator
from natureai_next.infrastructure.imaging.cache import DerivativeCache
from natureai_next.infrastructure.imaging.pillow_adapter import PillowImageDecoder
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend
from natureai_next.jobs.engine import JobEngine
from natureai_next.jobs.media_handlers import GenerateDerivativeHandler


def _library_service() -> LibraryService:
    return LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda clock, ids, schema: SqliteLibraryLifecycleBackend(clock, ids, schema),
    )


def test_photo_is_hidden_until_worker_commits_thumbnail_ready(tmp_path: Path) -> None:
    source = tmp_path / "photo.png"
    Image.new("RGB", (96, 64), "green").save(source)
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()

    with _library_service().open_or_create_clean(tmp_path / "Library") as opened:
        with opened.connection_factory.connect() as connection:
            asset_id = connection.execute(
                "INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us) "
                "VALUES('asset','image','active',1,1)"
            ).lastrowid
            file_id = connection.execute(
                "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,"
                "sha256,availability_state,created_at_us,modified_at_us,thumbnail_state) "
                "VALUES('file',?,'referenced','original',?,?,?,?, 'available',1,1,'imported')",
                (asset_id, str(source), str(source), source.stat().st_size, checksum),
            ).lastrowid
            connection.execute("UPDATE assets SET primary_file_instance_id=? WHERE id=?", (file_id, asset_id))
            connection.execute(
                "INSERT INTO image_properties(asset_id,file_instance_id,pixel_width,pixel_height) VALUES(?,?,96,64)",
                (asset_id, file_id),
            )
            connection.commit()

        catalog = SqliteCatalogGuiAdapter(opened.connection_factory)
        assert catalog.page_assets(limit=20).rows == ()

        jobs = JobService(SqliteJobCommandStore(opened.connection_factory), SystemClock(), SystemUuidGenerator())
        scheduler = DurableDerivativeScheduler(jobs)
        assert schedule_missing_photo_thumbnails(opened.connection_factory, scheduler) == 1

        engine = JobEngine(
            opened.connection_factory,
            [GenerateDerivativeHandler(
                DerivativeCache(opened.layout.thumbnails, PillowImageDecoder(), "thumbnail-lifecycle-test"),
                factory=opened.connection_factory,
                library_root=opened.layout.root,
            )],
            io_workers=0,
            cpu_workers=0,
        )
        assert engine.run_once(ResourceClass.IO)

        with opened.connection_factory.connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT thumbnail_state FROM file_instances WHERE id=?", (file_id,)
            ).fetchone()
            assert row["thumbnail_state"] == "ready"
        page = catalog.page_assets(limit=20)
        assert len(page.rows) == 1
        assert page.rows[0].thumbnail_path is not None


def test_failed_thumbnail_returns_to_imported_for_controlled_retry(tmp_path: Path) -> None:
    with _library_service().open_or_create_clean(tmp_path / "Library") as opened:
        missing = tmp_path / "missing.jpg"
        with opened.connection_factory.connect() as connection:
            asset_id = connection.execute(
                "INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us) "
                "VALUES('asset','image','active',1,1)"
            ).lastrowid
            file_id = connection.execute(
                "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,"
                "availability_state,created_at_us,modified_at_us,thumbnail_state) "
                "VALUES('file',?,'referenced','original',?,?,0,'available',1,1,'processing')",
                (asset_id, str(missing), str(missing)),
            ).lastrowid
            connection.commit()

        handler = GenerateDerivativeHandler(
            DerivativeCache(opened.layout.thumbnails, PillowImageDecoder(), "thumbnail-lifecycle-test"),
            factory=opened.connection_factory,
            library_root=opened.layout.root,
        )
        handler._set_state({"file_instance_id": file_id, "kind": "thumbnail"}, "failed")
        with opened.connection_factory.connect(read_only=True) as connection:
            assert connection.execute(
                "SELECT thumbnail_state FROM file_instances WHERE id=?", (file_id,)
            ).fetchone()[0] == "imported"
