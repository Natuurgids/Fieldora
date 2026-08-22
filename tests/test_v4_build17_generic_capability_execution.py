from pathlib import Path

import pytest

from natureai_next.application.capability_execution import (
    compatible_capabilities,
    validate_parameters,
)
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core.contracts import InputKind, ParameterDefinition
from natureai_next.synthesis_core.runtime import InProcessCapabilityRouter
from natureai_next.synthesis_core.test_sound import FixtureSoundEventCapability


def _workspace(tmp_path: Path) -> EnrichmentWorkspaceService:
    database_path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(database_path),), "4.0.0.dev1").activate(
        "enrichment"
    )
    router = InProcessCapabilityRouter()
    router.register(FixtureSoundEventCapability())
    return EnrichmentWorkspaceService(database_path, router, id_factory=lambda: "enr-build17")


def test_manifest_parameter_validation_normalizes_types_and_bounds():
    definitions = (
        ParameterDefinition("label", "string", required=True),
        ParameterDefinition("threshold", "float", minimum=0, maximum=1, default=0.5),
        ParameterDefinition("enabled", "boolean", default=True),
        ParameterDefinition("count", "integer", minimum=1, maximum=5, default=2),
    )
    assert validate_parameters(
        definitions, {"label": " bird ", "threshold": "0.75", "enabled": "false", "count": "3"}
    ) == {"label": "bird", "threshold": 0.75, "enabled": False, "count": 3}
    with pytest.raises(ValueError, match="threshold must be at most"):
        validate_parameters(definitions, {"label": "bird", "threshold": 2})
    with pytest.raises(ValueError, match="unknown parameters"):
        validate_parameters(definitions, {"label": "bird", "other": 1})


def test_capability_discovery_filters_by_subject_input_kind():
    descriptor = FixtureSoundEventCapability.descriptor
    assert [
        choice.descriptor.capability_id
        for choice in compatible_capabilities((descriptor,), InputKind.SOUND)
    ] == [descriptor.capability_id]
    assert compatible_capabilities((descriptor,), InputKind.VIDEO) == ()


def test_generic_workspace_execution_creates_pending_canonical_records(tmp_path: Path):
    workspace = _workspace(tmp_path)
    subject = SubjectRef(SubjectType.SOUND, "sound-17")
    outcome = workspace.run(
        subject,
        capability_id="aperture.fixture.sound-events",
        input_kind=InputKind.SOUND,
        structured_input={"events": [{"start_seconds": 1, "end_seconds": 2.5, "label": "call"}]},
        parameters={"default_label": "event"},
    )
    assert outcome.created_enrichment_ids == ("enr-build17",)
    assert len(outcome.projection.items) == 1
    assert outcome.projection.items[0].status == "pending_review"


def test_media_workspace_exposes_manifest_driven_execution_dialog():
    source = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    dialog = Path("src/natureai_next/ui/qt/capability_execution.py").read_text(encoding="utf-8")
    assert "Run enrichment…" in source
    assert "capabilities_for(input_kind)" in source
    assert "run_capability(" in source
    assert "CapabilityExecutionDialog" in dialog
    assert "validate_parameters" in dialog
    assert "Structured input (optional)" in dialog
