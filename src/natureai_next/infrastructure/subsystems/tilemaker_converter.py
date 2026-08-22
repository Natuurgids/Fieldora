"""Compatibility import for the Planetiler vector converter.

Tilemaker and the native PMTiles CLI are no longer used.
"""

from natureai_next.infrastructure.subsystems.planetiler_converter import PlanetilerVectorConverter


class TilemakerVectorConverter(PlanetilerVectorConverter):
    """Backward-compatible class name used by existing composition code."""

    def __init__(self, executable, expected_sha256="", config=None, process=None) -> None:
        super().__init__(executable.parent.parent)
