# Dynamic model plugins

Aperture discovers optional AI models from `src/natureai_next/resources/models.json` and from Python entry points in the `aperture.models` group. The existing BioCLIP/OpenCLIP provider remains the default catalog entry and continues to run through `LocalSuggestionGenerationService`; the catalog adapter only replaces the static provider construction at bootstrap.

## Catalog contract

Each model declares a stable string key, display metadata, `module:factory`, optional import/pip requirements, input parameters, canonical enrichment output fields, and a UI renderer hint. Model packages do not create authoritative databases. Generated results are normalized into Aperture's existing `enrichment_records`, `enrichment_values`, and `enrichment_labels` tables.

## Runtime

`DynamicModelManager` installs missing dependencies into a model-specific `models/runtime/<key>/site-packages` directory with the running Python interpreter. The directory is added to `sys.path`, import caches are invalidated, and the factory is imported with `importlib`, so Aperture does not need a restart. The Models settings page supports dependency installation, activation, deactivation, and optional deletion of the model runtime.

Turning a model off always unloads its resident objects and runs Python garbage collection. When PyTorch is available, Aperture also synchronizes CUDA and clears allocator and IPC caches. Choosing **Yes** in the deletion prompt removes only the model runtime and dependencies; choosing **No** retains them for later activation. Canonical enrichment is never removed.

## Third-party registration

A package may publish one model mapping, a sequence of mappings, or `ModelSpec` objects through:

```toml
[project.entry-points."aperture.models"]
my_model = "my_package.aperture_plugin:model_specs"
```

Factories used by the existing image-embedding pipeline must structurally implement the current `AIExecutionProvider` methods. Generic enrichment models may expose `load`, `infer`, and `unload`; `CatalogEnrichmentRunner` maps their declared fields into canonical enrichment.
