import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_optional_models_declare_offline_execution_contract():
    payload = json.loads((ROOT / 'src/natureai_next/resources/models.json').read_text())
    optional = [item for item in payload['models'] if not item.get('built_in')]
    assert optional
    assert all(item.get('offline_execution') is True for item in optional)
    assert all('enrichment performs no network access' in item.get('installation_contract','') for item in optional)


def test_megadetector_uses_supported_stable_artifact_and_not_removed_v6_url():
    worker = (ROOT / 'src/natureai_next/synthesis_core/optional_model_worker.py').read_text()
    assert 'agentmorris/MegaDetector/releases/download/v5.0/md_v5a.0.1.pt' in worker
    assert 'microsoft/MegaDetector/releases/download/v6.0.0' not in worker
    assert 'md_v6.0.0.pt' not in worker


def test_enrichment_workers_force_offline_mode():
    source = (ROOT / 'src/natureai_next/synthesis_core/optional_models.py').read_text()
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'KAGGLE_HUB_OFFLINE', 'APERTURE_MODEL_OFFLINE'):
        assert name in source
    assert 'if action.endswith("-run")' in source


def test_megadetector_artifact_is_persistent_not_temporary():
    worker = (ROOT / 'src/natureai_next/synthesis_core/optional_model_worker.py').read_text()
    assert '_ensure_megadetector_model(request)' in worker
    assert 'root / "md_v5a.0.1.pt"' in worker
