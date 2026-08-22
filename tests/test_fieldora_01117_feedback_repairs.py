from pathlib import Path
from types import SimpleNamespace

from natureai_next.infrastructure.database.suggestion_generation import (
    _active_photo_taxonomy_key,
)
from natureai_next.ui.qt.vector_map_view import vector_map_html


class _Catalog:
    def __init__(self, specs):
        self._specs = specs

    def get(self, key):
        return self._specs[key]


class _Manager:
    active_keys = frozenset({"provider", "capability"})

    def __init__(self):
        contract = {
            "asset_types": ["photo"],
        }
        output = {"enrichment_type": "taxonomy.classification"}
        self.catalog = _Catalog(
            {
                "provider": SimpleNamespace(
                    input_contract=contract, output_contract=output, built_in=True
                ),
                "capability": SimpleNamespace(
                    input_contract=contract, output_contract=output, built_in=False
                ),
            }
        )

    def instantiate(self, key):
        if key == "provider":
            return SimpleNamespace(load=lambda: None)
        return SimpleNamespace(
            descriptor=SimpleNamespace(capability_id="aperture.bioclip2"),
            execute=lambda _request: None,
        )


def test_provider_only_bioclip_does_not_replace_active_installed_package() -> None:
    assert _active_photo_taxonomy_key(_Manager()) == "capability"


def test_photo_review_reads_canonical_enrichment_database() -> None:
    source = Path("src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")
    assert 'media_name="Photos"' in source
    assert 'subject_type="photo"' in source
    assert 'self._tabs.addTab(photo_review, "Photos")' in source
    assert 'self._tabs.addTab(self._canonical_photo_review, "Photo Results")' in source


def test_offline_vector_map_renders_place_and_street_names_without_remote_glyphs() -> None:
    asset_root = Path("src/natureai_next/resources/map_renderer")
    document = vector_map_html("map-package", asset_root, base_url="http://127.0.0.1")
    assert "querySourceFeatures('aperture',{sourceLayer:'place'})" in document
    assert "['transportation_name','transportation']" in document
    assert "aperture-map-label" in document
    assert "apertureRefreshLabels" in document


def test_review_query_qualifies_enrichment_id_after_assignment_join() -> None:
    source = Path("src/natureai_next/ui/qt/knowledge_base.py").read_text(encoding="utf-8")
    assert "enrichment_records.enrichment_id AS enrichment_id" in source
