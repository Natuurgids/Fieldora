"""Desktop composition helpers for Aperture-owned enrichment workspaces."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from natureai_next.application.enrichment_ui import EnrichmentWorkspaceController
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core.runtime import InProcessCapabilityRouter
from natureai_next.synthesis_core.test_sound import FixtureSoundEventCapability


def build_desktop_enrichment_controller(
    database_path: Path,
    *,
    include_fixture_sound: bool = True,
) -> EnrichmentWorkspaceController:
    """Activate the fresh V4 store and compose a renderer/review controller.

    The router deliberately keeps the existing worker boundary untouched. Worker-backed
    capabilities can be registered later while projection and review remain available.
    """
    SubsystemDatabaseRegistry((enrichment_descriptor(database_path),), "4.0.0.dev1").activate(
        "enrichment"
    )
    router = InProcessCapabilityRouter()
    if include_fixture_sound:
        router.register(FixtureSoundEventCapability())
    workspace = EnrichmentWorkspaceService(
        database_path,
        router,
        id_factory=lambda: f"enr-{uuid4()}",
    )
    return EnrichmentWorkspaceController(workspace)
