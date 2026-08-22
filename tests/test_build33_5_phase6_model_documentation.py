import json
from pathlib import Path


def _catalog():
    path = Path(__file__).parents[1] / "src" / "natureai_next" / "resources" / "models.json"
    return json.loads(path.read_text(encoding="utf-8"))["models"]


def test_every_model_exposes_complete_workflow_documentation():
    required = {
        "purpose",
        "produces",
        "dependencies",
        "works_with",
        "workflow",
    }
    for model in _catalog():
        ui = model.get("ui", {})
        missing = required.difference(ui)
        assert not missing, f"{model['key']} missing UI documentation: {sorted(missing)}"
        assert ui["purpose"].strip()
        assert ui["produces"]
        assert ui["workflow"]


def test_model_outputs_remain_reviewable_and_provenance_aware():
    for model in _catalog():
        output = model.get("output", {})
        assert output.get("enrichment_type"), model["key"]
        assert output.get("review_mode"), model["key"]
        produces = " ".join(model["ui"]["produces"]).casefold()
        assert "provenance" in produces or "review" in produces
