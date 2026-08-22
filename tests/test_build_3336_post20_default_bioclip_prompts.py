import json
from pathlib import Path

from natureai_next.application.ai_setup import (
    BIOCLIP_DEFAULT_PROMPT_IDENTITY,
    BIOCLIP_DEFAULT_PROMPTS,
    BioCLIPQuickSetupService,
)


class _Resources:
    def __init__(self):
        self.installed = []

    def install_prompt_set(self, path: Path, *, model_family=None):
        self.installed.append((path, model_family))
        return "prompt-public-id"

    def build_taxonomy_embeddings(self):
        return (12, 12)


def test_default_natureai_prompt_profile_is_installed_and_embedded(tmp_path):
    resources = _Resources()
    manifest, public_id, counts = BioCLIPQuickSetupService(resources).install_default_prompt_set(
        tmp_path
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["identity"] == BIOCLIP_DEFAULT_PROMPT_IDENTITY
    assert payload["model_family"] == "bioclip"
    assert payload["prompts"] == list(BIOCLIP_DEFAULT_PROMPTS)
    assert resources.installed == [(manifest, "bioclip")]
    assert public_id == "prompt-public-id"
    assert counts == (12, 12)


def test_default_prompt_profile_contains_legacy_taxonomy_templates():
    texts = {item["text"] for item in BIOCLIP_DEFAULT_PROMPTS}
    assert "a photo of a {scientific_name}" in texts
    assert "a photo of a {common_name}" in texts
