from pathlib import Path

from natureai_next.synthesis_core.optional_model_worker import _taxonomy_candidates


def test_bioclip25_uses_openclip_and_matching_tree_of_life_embeddings():
    source = Path(
        "src/natureai_next/synthesis_core/optional_model_worker.py"
    ).read_text(encoding="utf-8")
    assert 'if provider == "bioclip25"' in source
    assert "_run_bioclip25_openclip" in source
    assert 'hf-hub:imageomics/bioclip-2.5-vith14' in source
    assert 'txt_emb_bioclip-2.5-vith14.npy' in source
    assert 'txt_emb_bioclip-2.5-vith14.json' in source
    assert "TreeOfLifeClassifier(model_str=model_str)" not in source


def test_bioclip25_taxonomy_candidates_preserve_hierarchy_and_probability():
    rows = [
        {
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "class": "Insecta",
            "order": "Hymenoptera",
            "family": "Apidae",
            "genus": "Apis",
            "species": "Apis mellifera",
            "common_name": "honey bee",
            "score": 0.75,
        }
    ]
    candidates = _taxonomy_candidates(rows, 10)
    assert candidates == [
        {
            "shape": "taxonomy_candidate",
            "payload": {
                "label": "honey bee",
                "scientific_name": "Apis mellifera",
                "common_name": "honey bee",
                "kingdom": "Animalia",
                "phylum": "Arthropoda",
                "class": "Insecta",
                "order": "Hymenoptera",
                "family": "Apidae",
                "genus": "Apis",
            },
            "confidence": 0.75,
            "target": {},
        }
    ]


def test_model_worker_uses_aperture_huggingface_cache_without_symlink_warning():
    source = Path("src/natureai_next/synthesis_core/optional_models.py").read_text(
        encoding="utf-8"
    )
    assert 'environment["HF_HOME"]' in source
    assert 'environment["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"' in source


def test_legacy_review_header_does_not_claim_to_be_capability_model():
    source = Path("src/natureai_next/ui/qt/ai_review.py").read_text(encoding="utf-8")
    assert "Current generation model (legacy suggestion engine)" in source
