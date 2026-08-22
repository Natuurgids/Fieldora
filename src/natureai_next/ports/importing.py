"""Ports used by the import application service."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from natureai_next.domain.importing import Fingerprint, SourceFile

CancelCheck = Callable[[], None]


class SourceScanner(Protocol):
    def scan(
        self, roots: Iterable[Path], *, recursive: bool, cancel: CancelCheck | None = None
    ) -> tuple[SourceFile, ...]: ...


class FileFingerprinter(Protocol):
    def fingerprint(self, path: Path, *, cancel: CancelCheck | None = None) -> Fingerprint: ...
    def fast_fingerprint(self, path: Path, *, cancel: CancelCheck | None = None) -> str: ...


class ManagedFileStore(Protocol):
    def place_verified(
        self, source: Path, sha256: str, *, cancel: CancelCheck | None = None
    ) -> Path: ...
    def purge(self, path: Path) -> None: ...


class SidecarResolver(Protocol):
    def companions(self, photo: Path) -> tuple[Path, ...]: ...


class ImportUnitOfWork(Protocol):
    connection: object
    assets: object
    files: object

    def commit(self) -> None: ...
    def __enter__(self): ...
    def __exit__(self, exc_type, exc, traceback) -> None: ...


ImportUnitOfWorkFactory = Callable[[], ImportUnitOfWork]
