from pathlib import Path

from natureai_next.application.ai_generation import LocalSuggestionGenerationService
from natureai_next.domain.ai import ActiveAIContext, EmbeddingVector


class Source:
    def __init__(self, path: Path):
        self.path = path

    def active_context(self):
        return ActiveAIContext(
            1, "BioCLIP", "2.0", "vit-b", "fp32", "prep", 224, self.path, "tol-10m", "cpu", "cpu"
        )

    def asset_paths(self, ids):
        return tuple((value, self.path) for value in ids)


class Repo:
    def begin_inference_run(self, **kwargs):
        return "run-1"

    def finish_inference_run(self, *args, **kwargs):
        pass


class Taxonomy:
    def candidates(self, **kwargs):
        return (("taxon:1", "Corvus corax", EmbeddingVector((1.0, 0.0))),)


class Suggestions:
    def create(self, **kwargs):
        return ("suggestion-1",)


class Provider:
    def load(self, *args, **kwargs):
        return object()

    def embed_images(self, model, images):
        return (EmbeddingVector((1.0, 0.0)),)

    def unload(self, model):
        pass


class Preprocessor:
    def prepare(self, path):
        return path


class Translator:
    def __init__(self):
        self.calls = []

    def translate(self, subject, result):
        self.calls.append((subject, result))
        return type("Outcome", (), {"enrichment_ids": ("enrichment-1",)})()


def test_legacy_bioclip_generation_mirrors_candidates_into_canonical_store(tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"photo")
    translator = Translator()
    service = LocalSuggestionGenerationService(
        source=Source(image),
        ai_repository=Repo(),
        taxonomy_embeddings=Taxonomy(),
        suggestions=Suggestions(),
        id_factory=lambda: "id-1",
        now_us=lambda: 1,
        provider=Provider(),
        preprocessor_factory=lambda *_: Preprocessor(),
        canonical_translation=translator,
    )

    result = service.generate_selected(("photo-1",), limit=1)

    assert result.suggestions_created == 1
    assert result.canonical_enrichment_created == 1
    subject, capability_result = translator.calls[0]
    assert subject.public_id == "photo-1"
    assert capability_result.capability_id == "aperture.bioclip"
    assert capability_result.candidates[0].value["scientific_name"] == "Corvus corax"
