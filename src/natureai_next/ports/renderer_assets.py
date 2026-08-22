"""Port for verifying bundled vector-renderer assets."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.maps import RendererAssetReadiness


class RendererAssetVerifier(Protocol):
    def verify(self, asset_root: Path) -> RendererAssetReadiness: ...
