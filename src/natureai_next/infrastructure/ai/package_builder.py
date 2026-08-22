"""Signed AI model-package builder adapter."""

from __future__ import annotations

from natureai_next.infrastructure.ai.package import build_model_package
from natureai_next.ports.model_packages import ModelPackageBuildRequest


class Ed25519ModelPackageBuilder:
    def build(self, request: ModelPackageBuildRequest) -> None:
        build_model_package(
            request.package_path,
            private_key=request.private_key,
            manifest=dict(request.manifest),
            artifacts=dict(request.artifacts),
        )
