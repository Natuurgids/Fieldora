import json
from pathlib import Path

from PIL import Image

from natureai_next.application.ai_generation import LocalSuggestionGenerationService
from natureai_next.domain.ai import ActiveAIContext, EmbeddingVector
from natureai_next.infrastructure.ai.preprocessing import BioClipImagePreprocessor


class Source:
    def __init__(self, path: Path): self.path = path
    def active_context(self):
        return ActiveAIContext(1, 'BioCLIP', '2.0', 'vit-b', 'fp32', 'prep', 224, self.path, 'prompts', 'cpu', 'cpu')
    def asset_paths(self, ids): return tuple((value, self.path) for value in ids)

class Repo:
    def begin_inference_run(self, **kwargs): return 'run-visual'
    def finish_inference_run(self, *args, **kwargs): pass

class Taxonomy:
    def candidates(self, **kwargs): return (('taxon:1', 'Species one', EmbeddingVector((1.0, 0.0))),)

class Suggestions:
    def __init__(self): self.kwargs = None
    def create(self, **kwargs): self.kwargs = kwargs; return ('suggestion-1',)

class Provider:
    def load(self, *args, **kwargs): return object()
    def embed_images(self, model, images): return (EmbeddingVector((1.0, 0.0)),)
    def unload(self, model): pass


def test_bioclip_generation_persists_model_input_snapshot(tmp_path):
    source = tmp_path / 'source.jpg'
    Image.new('RGB', (400, 300), 'white').save(source)
    suggestions = Suggestions()
    snapshot_root = tmp_path / 'library' / 'cache' / 'ai-inputs'
    service = LocalSuggestionGenerationService(
        source=Source(source), ai_repository=Repo(), taxonomy_embeddings=Taxonomy(),
        suggestions=suggestions, id_factory=lambda: 'id-1', now_us=lambda: 1,
        provider=Provider(), preprocessor_factory=lambda size, identity: BioClipImagePreprocessor(size, identity),
        inference_snapshot_root=snapshot_root,
    )
    service.generate_selected(('asset-1',), limit=1)
    provenance = suggestions.kwargs['provenance']
    snapshot = tmp_path / 'library' / provenance['inference_image_relative_path']
    assert snapshot.is_file()
    with Image.open(snapshot) as image:
        assert image.size == (224, 224)
    assert provenance['inference_image_width'] == 224
    assert provenance['inference_image_height'] == 224
