from pathlib import Path

from natureai_next.infrastructure.ai.engine_state import (
    NatureAIEngineState,
    read_engine_state,
    write_engine_state,
)


def test_natureai_state_round_trip(tmp_path: Path):
    path = tmp_path / "subsystems" / "natureai.sqlite"
    state = NatureAIEngineState(
        ready=True,
        engine_version="3.0.0rc1.post1",
        provider="pybioclip",
        model_identity="hf-hub:imageomics/bioclip",
        model_version="bioclip-v1",
        variant_identity="cuda-fp16",
        classifier="TreeOfLifeClassifier",
        taxonomy_source="TreeOfLife-10M",
        taxa_count=384490,
        device="cuda",
        updated_at_us=1,
    )
    write_engine_state(path, state)
    assert read_engine_state(path) == state


def test_generation_source_supports_external_natureai_engine():
    source = Path("src/natureai_next/infrastructure/database/suggestion_generation.py").read_text()
    assert 'external_engine") == "natureai"' in source
    assert 'classifier") == "TreeOfLifeClassifier"' in source
    assert 'Path("natureai-tree-of-life-managed")' in source


def test_desktop_registers_natureai_bridge():
    source = Path("src/natureai_next/bootstrap/cli.py").read_text()
    assert "read_engine_state" in source
    assert "ensure_aperture_bridge" in source
