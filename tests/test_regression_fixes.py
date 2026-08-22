from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.infrastructure.ai.package import build_model_package


def _manifest() -> dict[str, object]:
    return {
        "package_id": "same-package",
        "model_identity": "test-model",
        "semantic_version": "1.0.0",
        "model_family": "test",
        "upstream_source": "local",
        "license_name": "MIT",
        "attribution_text": "test",
        "minimum_application_version": "0.0.0",
        "signing_key_id": "local",
        "variants": [
            {
                "identity": "cpu",
                "runtime": "torch",
                "precision": "fp32",
                "providers": ["cpu"],
                "preprocessing_identity": "test-v1",
                "embedding_dimension": 2,
                "input_size": 2,
                "normalized_output": True,
                "artifact_path": "model.bin",
            }
        ],
    }


def test_model_package_build_is_reproducible(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    first = build_model_package(
        tmp_path / "first.zip",
        private_key=key,
        manifest=_manifest(),
        artifacts={"model.bin": b"same bytes"},
    )
    second = build_model_package(
        tmp_path / "second.zip",
        private_key=key,
        manifest=_manifest(),
        artifacts={"model.bin": b"same bytes"},
    )
    assert first.read_bytes() == second.read_bytes()


def test_planetiler_staging_keeps_mbtiles_suffix() -> None:
    source = Path("src/natureai_next/infrastructure/subsystems/planetiler_converter.py").read_text(
        encoding="utf-8"
    )
    assert ".converting.partial.mbtiles" in source


def test_notebook_reads_selection_before_save() -> None:
    source = Path("src/natureai_next/ui/qt/notebook.py").read_text(encoding="utf-8")
    method = source.split("def _page_selected", 1)[1].split("@Slot()", 1)[0]
    assert method.index("public_id =") < method.index("self._save_current")
    assert "refresh_list=False" in method


def test_offline_style_has_no_network_glyph_dependency() -> None:
    import json

    style = json.loads(
        Path("src/natureai_next/resources/map_renderer/aperture-streets-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert "glyphs" not in style
    assert all(layer.get("type") != "symbol" for layer in style["layers"])
    assert any(layer.get("source-layer") == "transportation" for layer in style["layers"])


def test_bioclip_downloader_preserves_resume_file() -> None:
    source = Path("src/natureai_next/application/ai_setup.py").read_text(encoding="utf-8")
    method = source.split("def _download", 1)[1].split("def _sha256_file", 1)[0]
    assert '.suffix + ".part"' in method
    assert 'headers["Range"]' in method
    assert "partial.unlink(missing_ok=True)" in method
    assert "will resume" in method


def test_planetiler_uses_global_source_lock_and_cleans_inprogress(tmp_path):
    from natureai_next.infrastructure.subsystems.planetiler_converter import (
        PlanetilerVectorConverter,
    )

    tool_root = tmp_path / "planetiler"
    source_root = tool_root / "sources"
    source_root.mkdir(parents=True)
    abandoned = source_root / "water-polygons-split-3857.zip_inprogress"
    abandoned.write_bytes(b"partial")
    reports = []
    with PlanetilerVectorConverter._shared_source_lock(
        tool_root, lambda c, t, m: reports.append(m), lambda: False
    ):
        PlanetilerVectorConverter._remove_stale_planetiler_downloads(source_root)
        assert not abandoned.exists()
        assert (tool_root / "sources.lock").exists()
    assert not (tool_root / "sources.lock").exists()


def test_vector_renderer_uses_direct_mbtiles_tile_template(tmp_path):
    from natureai_next.ui.qt.vector_map_view import vector_map_html

    assets = (
        Path(__file__).resolve().parents[1] / "src" / "natureai_next" / "resources" / "map_renderer"
    )
    document = vector_map_html("map:test", assets, longitude=6.5, latitude=52.0, zoom=12)
    assert "aperture-map://" in document
    assert "/tile/{z}/{x}/{y}.pbf" in document
    assert "pmtiles" not in document.casefold()


def test_planetiler_lock_covers_toolchain_download() -> None:
    source = Path("src/natureai_next/infrastructure/subsystems/planetiler_converter.py").read_text(
        encoding="utf-8"
    )
    lock_at = source.index("with self._shared_source_lock(tool_root, report, is_cancelled):")
    toolchain_at = source.index("java, jar = self._ensure_toolchain(tool_root, report)")
    assert lock_at < toolchain_at


def test_map_scheme_accepts_direct_tile_path():
    from natureai_next.ui.qt.map_archive_scheme import package_authority, package_id_from_scheme_url

    public_id = "map:test"
    authority = package_authority(public_id)
    assert package_id_from_scheme_url("aperture-map", authority, "/tile/0/0/0.pbf") == public_id


def test_vector_map_html_supports_same_origin_loopback_transport(tmp_path):
    from natureai_next.ui.qt.vector_map_view import vector_map_html

    asset_root = tmp_path
    (asset_root / "maplibre-gl.css").write_text("", encoding="utf-8")
    (asset_root / "maplibre-gl.js").write_text("", encoding="utf-8")
    # style loader uses the packaged style, so point to real assets instead.
    from pathlib import Path

    real_root = (
        Path(__file__).resolve().parents[1] / "src" / "natureai_next" / "resources" / "map_renderer"
    )
    document = vector_map_html("pkg-1", real_root, base_url="http://127.0.0.1:12345/token")
    assert "http://127.0.0.1:12345/token/tile/{z}/{x}/{y}.pbf" in document
    assert "aperture-map://" not in document


def test_vector_map_overlays_are_reasserted_as_foreground_after_style_changes():
    from natureai_next.ui.qt.vector_map_view import vector_map_html

    assets = (
        Path(__file__).resolve().parents[1] / "src" / "natureai_next" / "resources" / "map_renderer"
    )
    document = vector_map_html("map:test", assets)
    assert "window.apertureEnsureOverlays" in document
    assert "map.on('styledata'" in document
    assert "map.on('idle'" in document
    assert "map.moveLayer(id)" in document
    assert "apertureScheduleOverlayRestore" in document
    assert "map.on('style.load'" in document
    assert "map.setLayoutProperty(layer.id,'visibility','visible')" in document
    assert document.index("aperture-media-clusters") < document.index("aperture-media-counts")


def test_raster_map_canvas_uses_explicit_foreground_z_order():
    source = Path("src/natureai_next/ui/qt/maps.py").read_text(encoding="utf-8")
    assert "item.setZValue(-100.0)" in source
    assert "marker.setZValue(50.0)" in source
    assert "count.setZValue(51.0)" in source
    assert "line.setZValue(20.0)" in source
