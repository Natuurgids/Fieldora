"""Contracts for producing installable taxonomy packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from natureai_next.domain.taxonomy import LicenseMetadata


@dataclass(frozen=True, slots=True)
class TaxonomyPackageBuildRequest:
    package_path: Path
    private_key: object
    key_id: str
    package_id: str
    source_name: str
    source_version: str
    minimum_app_version: str
    license_metadata: LicenseMetadata
    taxa: Sequence[Mapping[str, object]]
    names: Sequence[Mapping[str, object]]
    regions: Sequence[Mapping[str, object]]
    attribution_text: str


class TaxonomyPackageBuilder(Protocol):
    """Build a signed taxonomy package from application-owned data."""

    def build(self, request: TaxonomyPackageBuildRequest) -> None: ...
