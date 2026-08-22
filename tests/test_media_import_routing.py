from __future__ import annotations

import os
import wave
from pathlib import Path

from natureai_next.application.import_service import ImportService
from natureai_next.application.library_service import LibraryService
from natureai_next.domain.importing import (
    DuplicatePolicy,
    ImportDecision,
    ImportSourceKind,
    ImportStoragePolicy,
    classify_import_source,
)
from natureai_next.infrastructure.database.catalog_gui import SqliteCatalogGuiAdapter
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.filesystem.importing import (
    DirectorySourceScanner,
    ShardedManagedFileStore,
    StreamingFileFingerprinter,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend
from natureai_next.ports.media import ImageProbe, MetadataResult


class _ImagesMustNotBeProbed:
    def probe(self, path: Path):
        raise AssertionError(f"non-image was sent to image decoder: {path}")


class _ImagesMustNotReadMetadata:
    def read(self, path: Path):
        raise AssertionError(f"non-image was sent to image metadata reader: {path}")


class _CountingFingerprinter(StreamingFileFingerprinter):
    def __init__(self) -> None:
        super().__init__()
        self.full_reads = 0
        self.fast_reads = 0

    def fingerprint(self, path: Path, *, cancel=None):
        self.full_reads += 1
        return super().fingerprint(path, cancel=cancel)

    def fast_fingerprint(self, path: Path, *, cancel=None) -> str:
        self.fast_reads += 1
        return super().fast_fingerprint(path, cancel=cancel)


class _TestImageServices:
    def __init__(self) -> None:
        self.probes = 0
        self.metadata_reads = 0

    def probe(self, _path: Path) -> ImageProbe:
        self.probes += 1
        return ImageProbe("JPEG", "image/jpeg", 1, 1, 1, None)

    def read(self, _path: Path) -> MetadataResult:
        self.metadata_reads += 1
        return MetadataResult({}, {})


def _library_service() -> LibraryService:
    return LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda c, i, s: SqliteLibraryLifecycleBackend(c, i, s),
    )


def test_media_extensions_are_classified_and_scanned(tmp_path: Path) -> None:
    expected = {
        "field.wav": ImportSourceKind.SOUND,
        "camera.mp4": ImportSourceKind.VIDEO,
        "notes.pdf": ImportSourceKind.DOCUMENT,
        "photo.jpg": ImportSourceKind.PHOTO,
    }
    for name, kind in expected.items():
        path = tmp_path / name
        path.write_bytes(b"sample")
        assert classify_import_source(path) is kind

    scanned = DirectorySourceScanner().scan((tmp_path,), recursive=True)
    assert {item.path.name for item in scanned} == set(expected)


def test_import_routes_sound_video_and_document_to_their_library_tables(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with wave.open(str(source / "field.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\0\0" * 800)
    (source / "camera.mp4").write_bytes(b"video fixture")
    (source / "notes.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    with _library_service().open_or_create_clean(tmp_path / "Library") as opened:
        fingerprinter = StreamingFileFingerprinter()
        service = ImportService(
            uow_factory=lambda: SqliteUnitOfWork(opened.connection_factory),
            scanner=DirectorySourceScanner(),
            fingerprinter=fingerprinter,
            managed_store=ShardedManagedFileStore(
                opened.layout.managed_originals, fingerprinter
            ),
            decoder=_ImagesMustNotBeProbed(),
            metadata_reader=_ImagesMustNotReadMetadata(),
            clock=SystemClock(),
            ids=SystemUuidGenerator(),
        )
        plan = service.plan(
            (source,),
            storage_policy=ImportStoragePolicy.MANAGED,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=frozenset(
                {
                    ImportSourceKind.SOUND,
                    ImportSourceKind.VIDEO,
                    ImportSourceKind.DOCUMENT,
                }
            ),
        )
        summary = service.execute(plan)
        assert summary.imported == 3
        assert summary.failed == 0

        with opened.connection_factory.connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT asset_type,original_filename FROM library_assets ORDER BY asset_type"
            ).fetchall()
            assert [(row["asset_type"], row["original_filename"]) for row in rows] == [
                ("document", "notes.pdf"),
                ("sound", "field.wav"),
                ("video", "camera.mp4"),
            ]
            assert connection.execute("SELECT COUNT(*) FROM sound_assets").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM video_assets").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM document_assets").fetchone()[0] == 1
            assert connection.execute(
                "SELECT duration_ms FROM sound_assets"
            ).fetchone()[0] == 100

        # The real workspace query must see the canonical media rows, while the
        # legacy Photos projection must exclude their compatibility placeholders.
        from natureai_next.application.media_queries import query_media_assets

        database = opened.connection_factory.database_path
        assert [row["original_filename"] for row in query_media_assets(database, asset_type="sound", detail_table="sound_assets", columns=("original_filename", "duration_ms"))] == ["field.wav"]
        assert [row["original_filename"] for row in query_media_assets(database, asset_type="video", detail_table="video_assets", columns=("original_filename", "duration_ms"))] == ["camera.mp4"]
        assert [row["original_filename"] for row in query_media_assets(database, asset_type="document", detail_table="document_assets", columns=("original_filename", "page_count"))] == ["notes.pdf"]
        assert SqliteCatalogGuiAdapter(opened.connection_factory).page_assets(limit=100).rows == ()


def test_import_type_selection_excludes_unchecked_media(tmp_path: Path) -> None:
    (tmp_path / "clip.mp4").write_bytes(b"video")
    (tmp_path / "notes.txt").write_text("document", encoding="utf-8")
    scanner = DirectorySourceScanner()
    scanned = scanner.scan((tmp_path,), recursive=True)
    selected = tuple(
        item
        for item in scanned
        if classify_import_source(item.path) in frozenset({ImportSourceKind.VIDEO})
    )
    assert [item.path.name for item in selected] == ["clip.mp4"]


def test_second_managed_import_skips_all_media_before_full_hash_or_probe(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "photo.jpg").write_bytes(b"photo fixture")
    with wave.open(str(source / "field.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\0\0" * 80)
    (source / "camera.mp4").write_bytes(b"video fixture")
    (source / "notes.txt").write_text("document fixture", encoding="utf-8")

    with _library_service().open_or_create_clean(tmp_path / "Library") as opened:
        fingerprinter = _CountingFingerprinter()
        image_services = _TestImageServices()
        service = ImportService(
            uow_factory=lambda: SqliteUnitOfWork(opened.connection_factory),
            scanner=DirectorySourceScanner(),
            fingerprinter=fingerprinter,
            managed_store=ShardedManagedFileStore(
                opened.layout.managed_originals, fingerprinter
            ),
            decoder=image_services,
            metadata_reader=image_services,
            clock=SystemClock(),
            ids=SystemUuidGenerator(),
        )
        kinds = frozenset(
            {
                ImportSourceKind.PHOTO,
                ImportSourceKind.SOUND,
                ImportSourceKind.VIDEO,
                ImportSourceKind.DOCUMENT,
            }
        )
        first = service.plan(
            (source,),
            storage_policy=ImportStoragePolicy.MANAGED,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=kinds,
        )
        first_summary = service.execute(first)
        assert first_summary.imported == 4
        full_reads_after_first = fingerprinter.full_reads
        probes_after_first = image_services.probes
        metadata_after_first = image_services.metadata_reads

        progress_messages: list[str] = []
        second = service.plan(
            (source,),
            storage_policy=ImportStoragePolicy.MANAGED,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=kinds,
            progress=lambda _current, _total, message: progress_messages.append(message),
        )
        second_summary = service.execute(second)

        assert all(
            item.decision is ImportDecision.SKIP_EXACT_DUPLICATE
            for item in second.items
        )
        assert second_summary.skipped == 4
        assert fingerprinter.full_reads == full_reads_after_first
        assert fingerprinter.fast_reads == 4
        assert image_services.probes == probes_after_first
        assert image_services.metadata_reads == metadata_after_first
        assert any("Unchanged duplicate 4 of 4" in message for message in progress_messages)

        # Size and timestamp alone are never trusted: a bounded head/tail
        # fingerprint mismatch falls back to the authoritative full checksum.
        photo = source / "photo.jpg"
        original_stat = photo.stat()
        photo.write_bytes(b"PHOTO fixture")
        os.utime(
            photo,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        third = service.plan(
            (source,),
            storage_policy=ImportStoragePolicy.MANAGED,
            duplicate_policy=DuplicatePolicy.SKIP,
            accepted_source_kinds=kinds,
        )
        photo_item = next(item for item in third.items if item.source.path == photo)
        assert photo_item.decision is ImportDecision.IMPORT_NEW_ASSET
        assert fingerprinter.full_reads == full_reads_after_first + 1
