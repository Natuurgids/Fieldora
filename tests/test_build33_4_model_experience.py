import json
from pathlib import Path

from natureai_next.infrastructure.ai.model_catalog import ModelCatalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'src' / 'natureai_next' / 'resources' / 'models.json'


def test_model_catalog_declares_purpose_workflow_and_dependencies():
    payload = json.loads(CATALOG.read_text(encoding='utf-8'))
    for item in payload['models']:
        ui = item.get('ui') or {}
        assert ui.get('category'), item['key']
        assert ui.get('purpose'), item['key']
        assert ui.get('workflow'), item['key']
        assert ui.get('dependencies') is not None, item['key']


def test_detection_and_segmentation_models_explain_bioclip_dependency():
    catalog = ModelCatalog.load(CATALOG, include_entry_points=False)
    for key in ('megadetector-v6', 'yolo11n-detect', 'yolo11n-segment'):
        spec = catalog.get(key)
        text = ' '.join(spec.ui_contract.get('dependencies', ())).casefold()
        assert 'bioclip' in text
    sam = catalog.get('sam-vit-b')
    workflow = ' '.join(sam.ui_contract.get('workflow', ())).casefold()
    assert 'bioclip' in workflow


def test_megadetector_is_described_as_camera_trap_localizer_not_species_classifier():
    catalog = ModelCatalog.load(CATALOG, include_entry_points=False)
    spec = catalog.get('megadetector-v6')
    purpose = spec.ui_contract['purpose'].casefold()
    assert 'camera-trap' in purpose
    assert 'does not identify species' in purpose


def test_model_manager_renders_workflow_dependency_sections():
    source = (ROOT / 'src' / 'natureai_next' / 'ui' / 'qt' / 'model_manager.py').read_text(encoding='utf-8')
    assert 'Workflow dependencies' in source
    assert 'Typical workflow' in source
    assert 'Works with' in source
    assert 'Offline ready' in source
