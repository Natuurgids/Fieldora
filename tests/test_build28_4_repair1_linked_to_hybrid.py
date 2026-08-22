from __future__ import annotations

import wave
from pathlib import Path

from natureai_next.application.import_service import ImportService
from natureai_next.application.library_service import LibraryService
from natureai_next.domain.importing import DuplicatePolicy, ImportSourceKind, ImportStoragePolicy
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.infrastructure.diagnostics.system_services import SystemClock, SystemUuidGenerator
from natureai_next.infrastructure.filesystem.importing import (
    DirectorySourceScanner,
    ShardedManagedFileStore,
    StreamingFileFingerprinter,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


class _NoImageDecoder:
    def probe(self, path: Path):
        raise AssertionError(f"sound file was sent to image decoder: {path}")


class _NoImageMetadata:
    def read(self, path: Path):
        raise AssertionError(f"sound file was sent to image metadata reader: {path}")


def test_linked_source_can_be_converted_to_hybrid_without_duplicate_path(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "field.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\0\0" * 800)

    library = LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda c, i, s: SqliteLibraryLifecycleBackend(c, i, s),
    )
    with library.open_or_create_clean(tmp_path / "Library") as opened:
        fingerprinter = StreamingFileFingerprinter()
        service = ImportService(
            uow_factory=lambda: SqliteUnitOfWork(opened.connection_factory),
            scanner=DirectorySourceScanner(),
            fingerprinter=fingerprinter,
            managed_store=ShardedManagedFileStore(opened.layout.managed_originals, fingerprinter),
            decoder=_NoImageDecoder(),
            metadata_reader=_NoImageMetadata(),
            clock=SystemClock(),
            ids=SystemUuidGenerator(),
        )
        linked = service.plan(
            (source_dir,),
            storage_policy=ImportStoragePolicy.REFERENCED,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=frozenset({ImportSourceKind.SOUND}),
        )
        first = service.execute(linked)
        assert first.imported == 1
        assert first.failed == 0

        hybrid = service.plan(
            (source_dir,),
            storage_policy=ImportStoragePolicy.HYBRID,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=frozenset({ImportSourceKind.SOUND}),
        )
        second = service.execute(hybrid)
        assert second.attached == 1
        assert second.failed == 0

        with opened.connection_factory.connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT storage_mode,path_key FROM file_instances ORDER BY id"
            ).fetchall()
            assert len(rows) == 2
            assert {row["storage_mode"] for row in rows} == {"referenced", "managed"}
            assert len({row["path_key"] for row in rows}) == 2
            assert connection.execute(
                "SELECT policy FROM asset_storage_policies"
            ).fetchone()["policy"] == "hybrid"
            locations = connection.execute(
                "SELECT role,provenance_role FROM asset_storage_locations ORDER BY role"
            ).fetchall()
            assert {(row["role"], row["provenance_role"]) for row in locations} == {
                ("source", "initial"),
                ("aperture_master", "managed_copy"),
            }
