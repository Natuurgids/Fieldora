from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from natureai_next.application.derivatives import DerivativeRequest, DurableDerivativeScheduler
from natureai_next.application.jobs import JobService
from natureai_next.application.library_service import LibraryService
from natureai_next.domain.jobs import ResourceClass
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
        backend_factory=lambda clock, ids, schema: SqliteLibraryLifecycleBackend(
            clock, ids, schema
        ),
    )


def test_missing_thumbnail_restarts_completed_job_and_repairs_stale_record(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (80, 60), "navy").save(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    with _library_service().open_or_create_clean(tmp_path / "Library") as opened:
        with opened.connection_factory.connect() as connection:
            asset_id = connection.execute(
                """INSERT INTO assets(
                    public_id,media_type,lifecycle_state,created_at_us,modified_at_us
                ) VALUES('asset','image','active',1,1)"""
            ).lastrowid
            file_id = connection.execute(
                """INSERT INTO file_instances(
                    public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,
                    sha256,availability_state,created_at_us,modified_at_us
                ) VALUES('file',?,'referenced','original',?,?,?,?,'available',1,1)""",
                (asset_id, str(source), str(source), source.stat().st_size, source_sha256),
            ).lastrowid
            connection.execute(
                "UPDATE assets SET primary_file_instance_id=? WHERE id=?",
                (file_id, asset_id),
            )
            connection.execute(
                """INSERT INTO image_properties(
                    asset_id,file_instance_id,pixel_width,pixel_height
                ) VALUES(?,?,80,60)""",
                (asset_id, file_id),
            )
            connection.commit()

        jobs = JobService(
            SqliteJobCommandStore(opened.connection_factory),
            SystemClock(),
            SystemUuidGenerator(),
        )
        scheduler = DurableDerivativeScheduler(jobs)
        request = DerivativeRequest(asset_id, file_id, source, source_sha256)
        engine = JobEngine(
            opened.connection_factory,
            [
                GenerateDerivativeHandler(
                    DerivativeCache(
                        opened.layout.thumbnails, PillowImageDecoder(), "thumbnail-recovery-test"
                    ),
                    factory=opened.connection_factory,
                    library_root=opened.layout.root,
                )
            ],
            io_workers=0,
            cpu_workers=0,
        )

        scheduler.schedule(request)
        assert engine.run_once(ResourceClass.IO)
        with opened.connection_factory.connect() as connection:
            row = connection.execute(
                "SELECT relative_path FROM derivative_cache_entries"
            ).fetchone()
            (opened.layout.root / row["relative_path"]).unlink()
            connection.execute("UPDATE derivative_cache_entries SET state='missing'")
            connection.commit()

        scheduler.schedule(request)
        with opened.connection_factory.connect(read_only=True) as connection:
            assert connection.execute(
                "SELECT state FROM jobs WHERE job_type='media.generate_derivative'"
            ).fetchone()["state"] == "queued"
        assert engine.run_once(ResourceClass.IO)
        with opened.connection_factory.connect(read_only=True) as connection:
            assert connection.execute(
                "SELECT state FROM derivative_cache_entries"
            ).fetchone()["state"] == "valid"
            assert connection.execute(
                "SELECT state FROM jobs WHERE job_type='media.generate_derivative'"
            ).fetchone()["state"] == "succeeded"


def test_derivative_handler_never_writes_job_states_into_cache_state() -> None:
    source = Path("src/natureai_next/jobs/media_handlers.py").read_text(encoding="utf-8")
    assert '"blocked_source_offline": "missing"' in source
    assert '"failed": "stale"' in source
    assert '"generating"' not in source[source.index("def _set_state") :]
