from __future__ import annotations

import json
from pathlib import Path

from natureai_next.infrastructure.ai.dynamic_model_manager import DynamicModelManager
from natureai_next.infrastructure.ai.model_catalog import ModelCatalog


def _catalog(tmp_path: Path, factory: str) -> ModelCatalog:
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "key": "test-model",
                        "display_name": "Test Model",
                        "factory": factory,
                        "default": True,
                        "input": {"parameters": {"limit": {"type": "integer", "default": 2}}},
                        "output": {
                            "enrichment_type": "test.result",
                            "fields": [{"key": "label", "type": "text", "label": True}],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return ModelCatalog.load(path, include_entry_points=False)


def test_catalog_loads_model_contract(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, "example:factory")
    spec = catalog.get("test-model")
    assert catalog.default_key == "test-model"
    assert spec.input_contract["parameters"]["limit"]["default"] == 2
    assert spec.output_contract["enrichment_type"] == "test.result"


def test_dynamic_manager_imports_activates_and_unloads_without_restart(
    tmp_path: Path, monkeypatch
) -> None:
    module = tmp_path / "demo_dynamic_model.py"
    module.write_text(
        """
class Demo:
    def __init__(self): self.unloaded = False
    def load(self, **kwargs): return {"loaded": True}
    def infer(self, inputs, parameters, model=None): return {"label": str(inputs), "confidence": 0.9}
    def unload(self, value=None): self.unloaded = True

def create(): return Demo()
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    manager = DynamicModelManager(
        _catalog(tmp_path, "demo_dynamic_model:create"), tmp_path / "runtime"
    )
    assert manager.active_key == "test-model"
    assert manager.missing_dependencies("test-model") == ()
    result = manager.infer("test-model", "bird", {})
    assert result["label"] == "bird"
    instance = manager.instantiate("test-model")
    manager.unload("test-model")
    assert instance.unloaded is True


def test_deactivate_can_delete_only_model_runtime(tmp_path: Path) -> None:
    manager = DynamicModelManager(_catalog(tmp_path, "builtins:dict"), tmp_path / "runtime")
    model_dir = manager.runtime_root / "test-model"
    model_dir.mkdir(parents=True)
    (model_dir / "cache.bin").write_bytes(b"x")
    manager.deactivate("test-model", delete_files=True)
    assert not model_dir.exists()
