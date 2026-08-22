"""Contracts for producing installable AI model packages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelPackageBuildRequest:
    package_path: Path
    private_key: object
    manifest: Mapping[str, object]
    artifacts: Mapping[str, bytes]


class ModelPackageBuilder(Protocol):
    def build(self, request: ModelPackageBuildRequest) -> None: ...
