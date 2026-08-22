"""Signed taxonomy-package builder adapter."""

from __future__ import annotations

from natureai_next.infrastructure.taxonomy.package import build_taxonomy_package
from natureai_next.ports.taxonomy_packages import TaxonomyPackageBuildRequest


class Ed25519TaxonomyPackageBuilder:
    """Adapt the existing Ed25519 ZIP builder to the application port."""

    def build(self, request: TaxonomyPackageBuildRequest) -> None:
        build_taxonomy_package(
            request.package_path,
            private_key=request.private_key,
            key_id=request.key_id,
            package_id=request.package_id,
            source_name=request.source_name,
            source_version=request.source_version,
            minimum_app_version=request.minimum_app_version,
            license_metadata=request.license_metadata,
            taxa=request.taxa,
            names=request.names,
            regions=request.regions,
            attribution_text=request.attribution_text,
        )
