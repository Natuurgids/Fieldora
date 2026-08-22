"""Runtime probe for the optional embedded vector-map renderer."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from natureai_next.domain.maps import VectorRendererReadiness
from natureai_next.infrastructure.subsystems.renderer_assets import Sha256RendererAssetVerifier
from natureai_next.ports.renderer_assets import RendererAssetVerifier


class QtWebEngineVectorRendererProbe:
    """Report concrete renderer prerequisites without activating a map view."""

    def __init__(
        self,
        asset_root: Path | None = None,
        *,
        archive_bridge_available: bool = False,
        asset_verifier: RendererAssetVerifier | None = None,
    ) -> None:
        configured = os.environ.get("APERTURE_VECTOR_RENDERER_ASSETS", "").strip()
        packaged = Path(__file__).resolve().parents[2] / "resources" / "map_renderer"
        self._asset_root = asset_root or (Path(configured) if configured else packaged)
        self._archive_bridge_available = archive_bridge_available
        self._asset_verifier = asset_verifier or Sha256RendererAssetVerifier()

    def readiness(self) -> VectorRendererReadiness:
        try:
            importlib.import_module("PySide6.QtWebEngineWidgets")
        except (ImportError, OSError) as exc:
            return VectorRendererReadiness(
                False,
                False,
                False,
                "renderer_runtime_missing",
                f"Qt WebEngine could not be loaded: {type(exc).__name__}",
            )

        if self._asset_root is None:
            return VectorRendererReadiness(
                True,
                False,
                False,
                "renderer_assets_missing",
                "Qt WebEngine is available; approved MapLibre renderer assets are not installed",
            )
        assets = self._asset_verifier.verify(self._asset_root)
        if not assets.valid:
            return VectorRendererReadiness(True, False, False, assets.status, assets.message)
        if not self._archive_bridge_available:
            return VectorRendererReadiness(
                True,
                True,
                False,
                "renderer_archive_bridge_missing",
                "Renderer assets are available; local MBTiles tile access is not installed",
            )
        return VectorRendererReadiness(
            True,
            True,
            True,
            "renderer_ready",
            "Street-level vector renderer prerequisites are available",
        )
