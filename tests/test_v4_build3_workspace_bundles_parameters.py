from __future__ import annotations

import hashlib
import json
from pathlib import Path

from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.application.source_lifecycle import SourceRegistryService, SourceState
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.plugins.bundles import OfflineBundleInstaller
from natureai_next.synthesis_core import (
    FixtureSoundEventCapability,
    InProcessCapabilityRouter,
    InputKind,
)
from natureai_next.synthesis_core.contracts import ParameterDefinition
from natureai_next.ui.enrichment.parameters import build_parameter_form


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def test_workspace_runs_projects_and_reviews_same_record(tmp_path: Path) -> None:
    database = _database(tmp_path)
    router = InProcessCapabilityRouter()
    router.register(FixtureSoundEventCapability())
    identifiers = iter(("enr-1", "enr-2"))
    service = EnrichmentWorkspaceService(database, router, id_factory=lambda: next(identifiers))
    subject = SubjectRef(SubjectType.SOUND, "sound-1")

    outcome = service.run(
        subject,
        capability_id="aperture.fixture.sound-events",
        input_kind=InputKind.SOUND,
        structured_input={"events": [{"start_seconds": 1, "end_seconds": 2.5, "label": "call"}]},
    )
    assert outcome.created_enrichment_ids == ("enr-1",)
    assert outcome.projection.pending[0].target == {"start_seconds": 1.0, "end_seconds": 2.5}

    projection = service.review(subject, "enr-1", EnrichmentStatus.ACCEPTED, reviewer="observer")
    assert projection.accepted[0].summary == "call"


def test_dynamic_parameter_form_validates_types_ranges_and_choices() -> None:
    form = build_parameter_form(
        (
            ParameterDefinition("top_k", "integer", default=10, minimum=1, maximum=50),
            ParameterDefinition("mode", "string", default="fast", choices=("fast", "accurate")),
            ParameterDefinition("enabled", "boolean", default=True),
        )
    )
    assert form.validate({"top_k": "12", "mode": "accurate", "enabled": "false"}) == {
        "top_k": 12,
        "mode": "accurate",
        "enabled": False,
    }


def test_offline_bundle_installer_verifies_and_registers_source(tmp_path: Path) -> None:
    database = _database(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    payload = bundle / "source.dat"
    payload.write_bytes(b"offline-source")
    checksum = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest = {
        "plugin_id": "org.aperture.test.source",
        "display_name": "Test Offline Source",
        "version": "1.0.0",
        "provider": "Aperture",
        "description": "Fixture source bundle",
        "license": "CC0-1.0",
        "plugin_api_specifier": ">=1,<2",
        "minimum_application_version": "4.0.0.dev1",
        "entry_point": "fixture:source",
        "kind": "source",
        "offline": True,
        "bundle_files": ["source.dat"],
        "checksums": {"source.dat": checksum},
        "attribution": "Aperture fixture",
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    registry = SourceRegistryService(database)
    installer = OfflineBundleInstaller(
        tmp_path / "installed",
        registry,
        api_version="1.0.0",
        application_version="4.0.0.dev1",
    )

    installed = installer.install(bundle)
    assert installed.verified_files == ("source.dat",)
    assert (installed.install_path / "source.dat").read_bytes() == b"offline-source"
    record = registry.get("org.aperture.test.source")
    assert record.state is SourceState.INSTALLED
    assert record.attribution == "Aperture fixture"
