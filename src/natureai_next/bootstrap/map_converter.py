"""Composition of Aperture's open-source Planetiler map builder."""

from __future__ import annotations

from pathlib import Path

from natureai_next.infrastructure.subsystems.planetiler_converter import PlanetilerVectorConverter


def create_packaged_tilemaker_converter() -> PlanetilerVectorConverter:
    """Retain the old factory name while composing the Planetiler adapter."""
    resources = Path(__file__).resolve().parents[1] / "resources"
    return PlanetilerVectorConverter(resources)
