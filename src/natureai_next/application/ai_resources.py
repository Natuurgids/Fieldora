"""Application facade for installed local AI resources."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from natureai_next.ports.ai_resources import AIResourceBackend
from natureai_next.ports.model_packages import ModelPackageBuilder, ModelPackageBuildRequest
from natureai_next.ports.taxonomy_packages import (
    TaxonomyPackageBuilder,
    TaxonomyPackageBuildRequest,
)


def load_trusted_key_file(path: Path) -> dict[str, bytes]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise ValueError("trusted key file must be a non-empty JSON object")
    result: dict[str, bytes] = {}
    for key_id, encoded in value.items():
        if not isinstance(key_id, str) or not key_id.strip() or not isinstance(encoded, str):
            raise ValueError("trusted key entries must map key identifiers to base64 strings")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != 32:
            raise ValueError(f"Ed25519 public key {key_id!r} must contain 32 bytes")
        result[key_id] = raw
    return result


class LocalAIResourceService:
    """Coordinates resource operations through injected adapters."""

    def __init__(
        self,
        *,
        backend: AIResourceBackend,
        model_package_builder: ModelPackageBuilder,
        taxonomy_package_builder: TaxonomyPackageBuilder,
    ) -> None:
        self._backend = backend
        self._model_package_builder = model_package_builder
        self._taxonomy_package_builder = taxonomy_package_builder

    def build_model_package(self, request: ModelPackageBuildRequest) -> None:
        self._model_package_builder.build(request)

    def build_taxonomy_package(self, request: TaxonomyPackageBuildRequest) -> None:
        self._taxonomy_package_builder.build(request)

    def install_model(self, package_path: Path, trusted_keys_path: Path) -> str:
        return self._backend.install_model(package_path, load_trusted_key_file(trusted_keys_path))

    def install_prompt_set(self, manifest_path: Path, *, model_family: str | None = None) -> str:
        return self._backend.install_prompt_set(manifest_path, model_family=model_family)

    def install_taxonomy(self, package_path: Path, trusted_keys_path: Path) -> str:
        return self._backend.install_taxonomy(
            package_path, load_trusted_key_file(trusted_keys_path)
        )

    def build_taxonomy_embeddings(self) -> tuple[int, int]:
        return self._backend.build_taxonomy_embeddings()
