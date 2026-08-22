from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from natureai_next.domain.enrichment import CanonicalShape
from natureai_next.infrastructure.ai.dynamic_model_manager import DynamicModelManager
from natureai_next.infrastructure.ai.model_catalog import ModelCatalog
from natureai_next.synthesis_core.optional_models import (
    _birdnet_candidates,
    _canonical_candidates,
    _speciesnet_candidates,
)
from natureai_next.synthesis_core.runtime import InProcessCapabilityRouter

ROOT = Path(__file__).resolve().parents[1]


def _optional_catalog(tmp_path: Path, factory: str) -> ModelCatalog:
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "key": "optional-test",
                        "display_name": "Optional Test",
                        "version": "1",
                        "factory": factory,
                        "license": "Test licence",
                        "requires_license_acceptance": True,
                        "estimated_download_mb": 12,
                        "default": True,
                        "built_in": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ModelCatalog.load(path, include_entry_points=False)


def test_catalog_offers_supported_birdnet_and_wildlife_video_models() -> None:
    catalog = ModelCatalog.load(
        ROOT / "src/natureai_next/resources/models.json", include_entry_points=False
    )
    birdnet = catalog.get("birdnet-v2.4")
    wildlife = catalog.get("wildlife-video-speciesnet-v5")

    assert birdnet.input_contract["asset_types"] == ["sound", "video"]
    assert birdnet.requires_license_acceptance is True
    assert birdnet.estimated_download_mb == 900
    assert wildlife.input_contract["asset_types"] == ["photo", "video"]
    assert wildlife.estimated_download_mb == 2500


def test_catalog_offers_new_field_validation_models() -> None:
    catalog = ModelCatalog.load(
        ROOT / "src/natureai_next/resources/models.json", include_entry_points=False
    )

    assert catalog.get("megadetector-v6").input_contract["asset_types"] == ["photo", "video"]
    assert catalog.get("bioclip-v2").factory.endswith(":BioCLIP2Capability")
    assert catalog.get("perch-v2").input_contract["asset_types"] == ["sound", "video"]
    assert catalog.get("batdetect2-v1").input_contract["asset_types"] == ["sound"]
    assert catalog.get("bioclip-v2.5-huge").estimated_download_mb == 7000


def test_external_worker_rows_become_canonical_candidates() -> None:
    candidates = _canonical_candidates(
        [
            {
                "shape": "bounding_box",
                "payload": {"label": "animal"},
                "confidence": 0.9,
                "target": {
                    "x": 0.1,
                    "y": 0.2,
                    "width": 0.3,
                    "height": 0.4,
                    "normalized": True,
                },
            }
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].shape is CanonicalShape.BOUNDING_BOX
    assert candidates[0].value["label"] == "animal"


def test_birdnet_csv_becomes_time_coded_canonical_candidates(tmp_path: Path) -> None:
    path = tmp_path / "sample.BirdNET.results.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Start (s)", "End (s)", "Scientific name", "Common name", "Confidence", "File"]
        )
        writer.writerow(["3", "6", "Turdus merula", "Common Blackbird", "0.91", "sample.wav"])

    candidates = _birdnet_candidates(path)

    assert len(candidates) == 1
    assert candidates[0].shape is CanonicalShape.TIME_SEGMENT
    assert candidates[0].target == {"start_seconds": 3.0, "end_seconds": 6.0}
    assert candidates[0].value["scientific_name"] == "Turdus merula"
    assert candidates[0].confidence == pytest.approx(0.91)


def test_speciesnet_predictions_become_spatiotemporal_review_candidates(
    tmp_path: Path,
) -> None:
    frame = tmp_path / "frame-000000030.jpg"
    predictions = {
        str(frame): {
            "prediction": "animal;mammalia;carnivora;canidae;Vulpes;Vulpes vulpes;Red fox",
            "prediction_score": 0.88,
            "detections": [{"label": "animal", "conf": 0.94, "bbox": [0.1, 0.2, 0.3, 0.4]}],
        }
    }

    candidates = _speciesnet_candidates(predictions, [(frame, 2.5)], 0.2)

    assert [candidate.shape for candidate in candidates] == [
        CanonicalShape.TAXONOMY_CANDIDATE,
        CanonicalShape.BOUNDING_BOX,
    ]
    assert candidates[0].value["scientific_name"] == "Vulpes vulpes"
    assert candidates[0].target["time_seconds"] == 2.5
    assert candidates[1].target["normalized"] is True


def test_load_model_requires_licence_health_checks_and_registers_capability(
    tmp_path: Path, monkeypatch
) -> None:
    module = tmp_path / "optional_provider.py"
    module.write_text(
        """
from natureai_next.synthesis_core.contracts import CapabilityDescriptor, CapabilityResult, InputKind
class Provider:
    descriptor = CapabilityDescriptor("test.optional", "Optional", "1", frozenset({InputKind.VIDEO}), frozenset({"label"}))
    def health_check(self): return "weights verified"
    def execute(self, request): return CapabilityResult("test.optional", "Optional", "1", ())
    def release(self): pass
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    router = InProcessCapabilityRouter()
    manager = DynamicModelManager(
        _optional_catalog(tmp_path, "optional_provider:Provider"),
        tmp_path / "runtime",
        capability_router=router,
    )

    with pytest.raises(PermissionError, match="licence acceptance"):
        manager.install_model("optional-test")
    result = manager.install_model("optional-test", accept_license=True)
    assert result.health_detail == "weights verified"
    assert manager.is_installed("optional-test") is True

    manager.activate("optional-test")
    assert "optional-test" in manager.active_keys
    assert [item.capability_id for item in router.discover()] == ["test.optional"]


def test_failed_health_check_never_marks_model_installed(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "broken_provider.py"
    module.write_text(
        """
class Provider:
    def health_check(self): raise RuntimeError("invalid weights")
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    manager = DynamicModelManager(
        _optional_catalog(tmp_path, "broken_provider:Provider"), tmp_path / "runtime"
    )

    with pytest.raises(RuntimeError, match="invalid weights"):
        manager.install_model("optional-test", accept_license=True)

    assert manager.is_installed("optional-test") is False
    assert not (manager.runtime_root / ".optional-test.installing").exists()


def test_models_workspace_exposes_load_model_health_installation() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")

    assert 'QPushButton("Load model…")' in source
    assert "install_model(" in source
    assert "passed its health check" in source


def test_optional_core_adapter_does_not_enter_gui_import_path(tmp_path: Path) -> None:
    catalog = ModelCatalog.load(
        ROOT / "src/natureai_next/resources/models.json", include_entry_points=False
    )
    manager = DynamicModelManager(catalog, tmp_path / "runtime")
    dependency_root = manager.runtime_root / "birdnet-v2.4" / "site-packages"
    dependency_root.mkdir(parents=True)

    manager.instantiate("birdnet-v2.4")

    assert str(dependency_root) not in sys.path


def test_speciesnet_worker_uses_supported_command_interface() -> None:
    source = (ROOT / "src/natureai_next/synthesis_core/optional_model_worker.py").read_text(
        encoding="utf-8"
    )

    assert '"speciesnet.scripts.run_model"' in source
    assert '"--predictions_json"' in source


def test_install_health_check_receives_cancellation_context(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "context_provider.py"
    module.write_text(
        """
class Provider:
    def health_check_with_context(self, *, cancellation, progress):
        assert cancellation() is False
        progress(3, 4, "context health")
        return "context verified"
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    manager = DynamicModelManager(
        _optional_catalog(tmp_path, "context_provider:Provider"), tmp_path / "runtime"
    )
    messages = []

    result = manager.install_model(
        "optional-test",
        accept_license=True,
        cancellation=lambda: False,
        progress=lambda _current, _total, message: messages.append(message),
    )

    assert result.health_detail == "context verified"
    assert "context health" in messages


def test_perch_catalog_includes_kagglehub_dependency() -> None:
    document = json.loads(
        (Path(__file__).parents[1] / "src/natureai_next/resources/models.json").read_text(
            encoding="utf-8"
        )
    )
    perch = next(item for item in document["models"] if item["key"] == "perch-v2")
    imports = {item["import"]: item["pip"] for item in perch["requirements"]}
    assert imports["kagglehub"] == "kagglehub"


def test_perch_health_and_execution_share_initializer() -> None:
    source = (
        Path(__file__).parents[1]
        / "src/natureai_next/synthesis_core/optional_model_worker.py"
    ).read_text(encoding="utf-8")
    assert "model = _initialize_perch2()" in source
    assert source.count("model = _initialize_perch2()") == 2
    assert "return model_zoo.Perch2()" in source
