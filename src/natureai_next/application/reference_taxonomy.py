"""Application service for authoritative shared taxonomy packages."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.taxonomy import TaxonomyPackageData


class VerifiedPackageReader(Protocol):
    def verify(self, path: Path) -> TaxonomyPackageData: ...


class ReferencePackageCatalog(Protocol):
    def install_verified_package(
        self, package: TaxonomyPackageData, *, installed_at_us: int, source_url: str | None = None
    ) -> str: ...


class AuthoritativeTaxonomyImportService:
    def __init__(self, verifier: VerifiedPackageReader, catalog: ReferencePackageCatalog) -> None:
        self._verifier = verifier
        self._catalog = catalog

    def install(self, path: Path, *, installed_at_us: int, source_url: str | None = None) -> str:
        package = self._verifier.verify(path)
        if not package.license.redistribution_allowed:
            raise ValueError("taxonomy package licence does not permit redistribution")
        return self._catalog.install_verified_package(
            package, installed_at_us=installed_at_us, source_url=source_url
        )
