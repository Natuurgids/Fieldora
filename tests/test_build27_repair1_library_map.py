from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_inspector_does_not_render_redundant_preview():
    source = (ROOT / 'src/natureai_next/ui/qt/library.py').read_text(encoding='utf-8')
    assert 'right_layout.addWidget(self._preview' not in source
    assert 'worker = _PreviewWorker(' not in source[source.index('def _detail_ready'):source.index('def _preview_ready')]


def test_batch_editor_exposes_single_photo_metadata_fields():
    source = (ROOT / 'src/natureai_next/ui/qt/library.py').read_text(encoding='utf-8')
    for label in ('Title', 'Caption', 'Notes', 'Rating', 'Color', 'Pick state', 'User tags', 'Subject location name', 'Subject latitude', 'Subject longitude'):
        assert f'"{label}"' in source
    assert '_BatchReviewWorker(self._catalog, self._editor' in source


def test_map_asset_queries_do_not_depend_on_rtree_freshness():
    source = (ROOT / 'src/natureai_next/infrastructure/database/spatial_intelligence.py').read_text(encoding='utf-8')
    asset_section = source[source.index('def assets_in_bounds'):source.index('def list_sites_in_bounds')]
    assert 'FROM locations l' in asset_section
    assert 'l.latitude BETWEEN ? AND ?' in asset_section
    assert 'FROM location_rtree' not in asset_section
