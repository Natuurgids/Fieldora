"""Port for probing the optional street-level map renderer."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.maps import VectorRendererReadiness


class VectorRendererProbe(Protocol):
    def readiness(self) -> VectorRendererReadiness: ...
