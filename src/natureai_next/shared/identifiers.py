"""Stable semantic identifiers used across architectural boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DOTTED_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")


@dataclass(frozen=True, slots=True)
class SemanticId:
    """Validated lowercase dotted or namespaced identifier."""

    value: str

    def __post_init__(self) -> None:
        if not _DOTTED_ID.fullmatch(self.value):
            raise ValueError(f"Invalid semantic identifier: {self.value!r}")

    def __str__(self) -> str:
        return self.value
