"""Installed local-AI resource operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AIResourceBackend(Protocol):
    def install_model(self, package_path: Path, trusted_keys: dict[str, bytes]) -> str: ...
    def install_prompt_set(
        self, manifest_path: Path, *, model_family: str | None = None
    ) -> str: ...
    def install_taxonomy(self, package_path: Path, trusted_keys: dict[str, bytes]) -> str: ...
    def build_taxonomy_embeddings(self) -> tuple[int, int]: ...
