from pathlib import Path


def test_adapter_pins_original_bioclip_model() -> None:
    source = Path("src/natureai_next/infrastructure/ai/tree_of_life_classifier.py").read_text()
    assert "BIOCLIP_V1_MODEL_STR" in source
    assert "model_str=BIOCLIP_V1_MODEL_STR" in source


def test_quick_setup_bootstraps_tree_of_life_without_csv() -> None:
    source = Path("src/natureai_next/application/ai_setup.py").read_text()
    assert "bootstrap_tree_of_life_resources" in source
    assert "build_aperture_embeddings=False" in source
    assert "tree_of_life_ready" in source


def test_full_ai_installer_includes_and_bootstraps_pybioclip() -> None:
    source = Path("scripts/install_windows.ps1").read_text()
    assert "pybioclip==2.1.5" in source
    assert "bootstrap_bioclip_tree_of_life.py" in source


def test_bootstrap_rejects_empty_label_table() -> None:
    source = Path("src/natureai_next/infrastructure/ai/tree_of_life_resources.py").read_text()
    assert "empty Tree-of-Life label table" in source
    assert "TreeOfLifeClassifier" in source
