from natureai_next.plugin_api import PluginKind
from natureai_next.plugins.manifest import parse_manifest


def test_manifest_v2_describes_capability_outputs_and_offline_bundle() -> None:
    manifest = parse_manifest(
        {
            "plugin_id": "org.aperture.bioclip",
            "display_name": "BioCLIP",
            "version": "4.0.0.dev1",
            "provider": "Aperture",
            "description": "Offline photo taxonomy capability",
            "license": "MIT",
            "plugin_api_specifier": ">=1,<2",
            "minimum_application_version": "4.0.0.dev1",
            "entry_point": "aperture_bioclip:plugin",
            "capabilities": ["ai.model_loading"],
            "kind": "capability",
            "input_kinds": ["photo"],
            "output_shapes": ["taxonomy_candidate", "label"],
            "parameters": [{"name": "top_k", "type": "integer", "default": 5}],
            "offline": True,
            "bundle_files": ["wheels/pybioclip.whl", "models/bioclip.bin"],
            "checksums": {"models/bioclip.bin": "sha256:abc"},
            "attribution": "BioCLIP contributors",
        }
    )
    assert manifest.kind is PluginKind.CAPABILITY
    assert manifest.input_kinds == ("photo",)
    assert manifest.output_shapes == ("taxonomy_candidate", "label")
    assert manifest.offline is True
    assert manifest.checksums["models/bioclip.bin"] == "sha256:abc"
