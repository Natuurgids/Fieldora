from pathlib import Path

from natureai_next.infrastructure.ai.tree_of_life_classifier import TreeOfLifeClassifierAdapter


def test_tree_of_life_adapter_builds_candidates_from_legacy_rows(
    monkeypatch, tmp_path: Path
) -> None:
    adapter = TreeOfLifeClassifierAdapter(device="cpu")

    class FakeClassifier:
        def predict(self, paths, *, rank, k, batch_size):
            assert paths == [str(tmp_path / "bird.jpg")]
            assert k == 3
            return [
                {
                    "scientific_name": "Turdus merula",
                    "common_name": "Common blackbird",
                    "score": 0.42,
                    "rank": "species",
                    "taxon_id": "2490719",
                }
            ]

    adapter._classifier = FakeClassifier()
    result = adapter.predict(tmp_path / "bird.jpg", limit=3)
    assert result[0].label == "Turdus merula (Common blackbird)"
    assert result[0].taxon_public_id is None
    assert result[0].calibrated_score is None
    assert adapter.last_prediction_rows[0]["taxon_id"] == "2490719"
    assert result[0].taxonomic_level == "species"


def test_generation_source_contains_tree_of_life_fallback() -> None:
    source = Path("src/natureai_next/application/ai_generation.py").read_text(encoding="utf-8")
    assert "use_tree_of_life = not candidates" in source
    assert "TreeOfLifeClassifierAdapter" in source


def test_tree_of_life_predict_supplies_streams_for_windowless_gui(
    monkeypatch, tmp_path: Path
) -> None:
    import sys

    adapter = TreeOfLifeClassifierAdapter(device="cpu")

    class FakeClassifier:
        def predict(self, paths, *, rank, k, batch_size):
            sys.stdout.write("progress")
            sys.stderr.write("diagnostic")
            return [{"scientific_name": "Turdus merula", "score": 0.42}]

    adapter._classifier = FakeClassifier()
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    result = adapter.predict(tmp_path / "bird.jpg", limit=1)
    assert result[0].label == "Turdus merula"
    assert sys.stdout is None
    assert sys.stderr is None
