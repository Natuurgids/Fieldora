"""Bounded source scanning, streaming fingerprints and immutable managed originals."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from defusedxml import ElementTree

from natureai_next.domain.importing import (
    PHOTO_EXTENSIONS,
    RAW_EXTENSIONS,
    Fingerprint,
    ImportSourceKind,
    SourceFile,
    classify_import_source,
)
from natureai_next.ports.importing import CancelCheck


class DarwinCoreArchiveError(ValueError):
    """Raised when a ZIP is not a safe, usable Darwin Core Archive."""


class DarwinCoreArchiveExpander:
    """Validate and safely stage embedded media from an unmodified DwC-A ZIP.

    The original archive is never rewritten. Staging is deterministic for a
    given archive path/size/mtime so a persisted import plan can be executed
    after planning without depending on an ephemeral TemporaryDirectory.
    """

    def __init__(
        self,
        cache_root: Path | None = None,
        *,
        max_members: int = 1_000_000,
        max_uncompressed_bytes: int = 200 * 1024**3,
    ) -> None:
        self.cache_root = cache_root or Path(tempfile.gettempdir()) / "aperture-dwca"
        self.max_members = max_members
        self.max_uncompressed_bytes = max_uncompressed_bytes

    def is_dwca(self, path: Path) -> bool:
        if path.suffix.casefold() != ".zip":
            return False
        try:
            with zipfile.ZipFile(path) as archive:
                return any(
                    PureArchivePath(info.filename).name.casefold() == "meta.xml"
                    for info in archive.infolist()
                )
        except (OSError, zipfile.BadZipFile):
            return False

    def expand(self, path: Path, *, cancel: CancelCheck | None = None) -> tuple[Path, ...]:
        path = path.expanduser().resolve()
        stat = path.stat()
        key = hashlib.sha256(f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()).hexdigest()
        destination = self.cache_root / key
        manifest_path = destination / ".aperture-dwca.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                media = tuple(destination / item for item in manifest.get("media", ()))
                if media and all(item.is_file() for item in media):
                    return media
            except (OSError, ValueError, TypeError):
                pass

        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > self.max_members:
                raise DarwinCoreArchiveError(
                    "Darwin Core Archive exceeds the configured member limit"
                )
            total = sum(max(0, info.file_size) for info in infos)
            if total > self.max_uncompressed_bytes:
                raise DarwinCoreArchiveError(
                    "Darwin Core Archive exceeds the configured expanded-size limit"
                )
            meta = next(
                (
                    info
                    for info in infos
                    if PureArchivePath(info.filename).name.casefold() == "meta.xml"
                ),
                None,
            )
            if meta is None:
                raise DarwinCoreArchiveError("ZIP does not contain Darwin Core Archive meta.xml")
            try:
                root = ElementTree.fromstring(archive.read(meta))
            except (ElementTree.ParseError, OSError, KeyError) as exc:
                raise DarwinCoreArchiveError("Darwin Core Archive meta.xml is invalid") from exc
            if not any(_xml_local_name(node.tag) == "core" for node in root.iter()):
                raise DarwinCoreArchiveError(
                    "Darwin Core Archive meta.xml does not declare a core data file"
                )

            media: list[Path] = []
            for info in infos:
                if cancel:
                    cancel()
                member = PureArchivePath(info.filename)
                if info.is_dir() or not _safe_archive_member(member):
                    continue
                if Path(member.name).suffix.casefold() not in PHOTO_EXTENSIONS | RAW_EXTENSIONS:
                    continue
                target = destination.joinpath(*member.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.open(info) as source,
                    NamedTemporaryFile(
                        dir=target.parent,
                        prefix=f".{target.name}.",
                        suffix=".partial",
                        delete=False,
                    ) as temp,
                ):
                    temp_path = Path(temp.name)
                    while chunk := source.read(4 * 1024 * 1024):
                        if cancel:
                            cancel()
                        temp.write(chunk)
                os.replace(temp_path, target)
                media.append(target)

        relative = [str(item.relative_to(destination)) for item in sorted(media)]
        manifest_path.write_text(
            json.dumps({"source_archive": str(path), "media": relative}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if not media:
            raise DarwinCoreArchiveError(
                "Darwin Core Archive is valid but contains no embedded image files; remote media references are not downloaded automatically"
            )
        return tuple(sorted(media, key=lambda item: os.path.normcase(str(item))))


class PureArchivePath:
    """Small POSIX archive path wrapper that rejects platform path quirks."""

    def __init__(self, value: str) -> None:
        normalized = value.replace("\\", "/")
        self.absolute = normalized.startswith("/")
        self.parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
        self.name = self.parts[-1] if self.parts else ""


def _safe_archive_member(path: PureArchivePath) -> bool:
    return (
        bool(path.parts)
        and not path.absolute
        and ".." not in path.parts
        and not path.parts[0].endswith(":")
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


class DirectorySourceScanner:
    def __init__(
        self, *, max_files: int = 1_000_000, dwca_expander: DarwinCoreArchiveExpander | None = None
    ) -> None:
        self.max_files = max_files
        # Darwin Core media extraction is opt-in only. The normal Library photo
        # importer must remain a pure filesystem photo scanner. Taxonomy import
        # is owned by the independent taxonomy workflow.
        self.dwca_expander = dwca_expander

    def scan(
        self, roots: Iterable[Path], *, recursive: bool, cancel: CancelCheck | None = None
    ) -> tuple[SourceFile, ...]:
        found: list[SourceFile] = []
        seen: set[str] = set()
        for root in roots:
            root = root.expanduser().resolve()
            candidates = (
                root.rglob("*")
                if recursive and root.is_dir()
                else (root.iterdir() if root.is_dir() else (root,))
            )
            for path in candidates:
                if cancel:
                    cancel()
                if not path.is_file() or path.is_symlink():
                    continue
                if self.dwca_expander is not None and self.dwca_expander.is_dwca(path):
                    for media_path in self.dwca_expander.expand(path, cancel=cancel):
                        media_stat = media_path.stat()
                        media_key = os.path.normcase(str(media_path.resolve())).casefold()
                        if media_key not in seen:
                            seen.add(media_key)
                            found.append(
                                SourceFile(
                                    media_path.resolve(),
                                    media_stat.st_size,
                                    media_stat.st_mtime_ns // 1000,
                                )
                            )
                            if len(found) > self.max_files:
                                raise ValueError("source scan exceeded configured file limit")
                    continue
                # Metadata sidecars are resolved as companions. Unknown files,
                # archives and databases remain outside the media library.
                source_kind = classify_import_source(path)
                if source_kind not in (
                    ImportSourceKind.PHOTO,
                    ImportSourceKind.RAW_PHOTO,
                    ImportSourceKind.SOUND,
                    ImportSourceKind.VIDEO,
                    ImportSourceKind.DOCUMENT,
                ):
                    continue
                path_key = os.path.normcase(str(path.resolve())).casefold()
                if path_key in seen:
                    continue
                seen.add(path_key)
                stat = path.stat()
                found.append(SourceFile(path.resolve(), stat.st_size, stat.st_mtime_ns // 1000))
                if len(found) > self.max_files:
                    raise ValueError("source scan exceeded configured file limit")
        found.sort(key=lambda item: os.path.normcase(str(item.path)))
        return tuple(found)


class XmpSidecarResolver:
    """Find conventional XMP companions without recursive or unbounded scanning."""

    def __init__(self, *, max_directory_entries: int = 100_000) -> None:
        self.max_directory_entries = max_directory_entries

    def companions(self, photo: Path) -> tuple[Path, ...]:
        expected = {f"{photo.name}.xmp".casefold(), f"{photo.stem}.xmp".casefold()}
        found: list[Path] = []
        try:
            entries = photo.parent.iterdir()
            for index, candidate in enumerate(entries):
                if index >= self.max_directory_entries:
                    break
                if candidate.name.casefold() not in expected:
                    continue
                if candidate.is_file() and not candidate.is_symlink():
                    found.append(candidate.resolve())
        except OSError:
            return ()
        return tuple(sorted(set(found), key=lambda path: os.path.normcase(str(path))))


class StreamingFileFingerprinter:
    def __init__(self, *, chunk_size: int = 4 * 1024 * 1024, fast_window: int = 64 * 1024) -> None:
        self.chunk_size = chunk_size
        self.fast_window = fast_window

    def fingerprint(self, path: Path, *, cancel: CancelCheck | None = None) -> Fingerprint:
        stat_before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(self.chunk_size):
                if cancel:
                    cancel()
                digest.update(chunk)
        stat_after = path.stat()
        if (stat_before.st_size, stat_before.st_mtime_ns) != (
            stat_after.st_size,
            stat_after.st_mtime_ns,
        ):
            raise OSError(f"source changed while hashing: {path}")
        fast = self._fast(path, stat_after.st_size)
        return Fingerprint(digest.hexdigest(), stat_after.st_size, fast)

    def fast_fingerprint(self, path: Path, *, cancel: CancelCheck | None = None) -> str:
        """Read only bounded head/tail windows for safe incremental import checks."""
        stat_before = path.stat()
        if cancel:
            cancel()
        digest = self._fast(path, stat_before.st_size)
        if cancel:
            cancel()
        stat_after = path.stat()
        if (stat_before.st_size, stat_before.st_mtime_ns) != (
            stat_after.st_size,
            stat_after.st_mtime_ns,
        ):
            raise OSError(f"source changed while fingerprinting: {path}")
        return digest

    def _fast(self, path: Path, size: int) -> str:
        digest = hashlib.blake2b(digest_size=16)
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            digest.update(stream.read(self.fast_window))
            if size > self.fast_window:
                stream.seek(max(0, size - self.fast_window))
                digest.update(stream.read(self.fast_window))
        return digest.hexdigest()


class ShardedManagedFileStore:
    def __init__(self, root: Path, fingerprinter: StreamingFileFingerprinter) -> None:
        self.root = root
        self.fingerprinter = fingerprinter

    def path_for(self, sha256: str, suffix: str) -> Path:
        safe_suffix = suffix.lower() if suffix and len(suffix) <= 16 else ""
        return self.root / sha256[:2] / sha256[2:4] / f"{sha256}{safe_suffix}"

    def place_verified(
        self, source: Path, sha256: str, *, cancel: CancelCheck | None = None
    ) -> Path:
        destination = self.path_for(sha256, source.suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if self.fingerprinter.fingerprint(destination, cancel=cancel).sha256 != sha256:
                raise OSError(f"managed original checksum conflict: {destination}")
            return destination
        with NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".partial", delete=False
        ) as temp:
            temp_path = Path(temp.name)
            with source.open("rb") as input_stream:
                while chunk := input_stream.read(self.fingerprinter.chunk_size):
                    if cancel:
                        cancel()
                    temp.write(chunk)
            temp.flush()
            os.fsync(temp.fileno())
        try:
            if self.fingerprinter.fingerprint(temp_path, cancel=cancel).sha256 != sha256:
                raise OSError("managed copy verification failed")
            os.replace(temp_path, destination)
            with suppress(OSError):
                destination.chmod(0o444)
            return destination
        finally:
            temp_path.unlink(missing_ok=True)

    def purge(self, path: Path) -> None:
        with suppress(OSError):
            path.chmod(0o666)
        path.unlink(missing_ok=True)
