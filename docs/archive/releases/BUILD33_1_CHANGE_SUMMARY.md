# Build 33.1 Change Summary

Build 33.1 is a focused BioCLIP runtime and provenance repair.

## Repairs

- BioCLIP 2.5 Huge now runs through its supported OpenCLIP ViT-H/14 runtime.
- Taxonomy ranking uses the matching Imageomics TreeOfLife-200M BioCLIP 2.5 text embeddings and label file.
- BioCLIP 2 remains on pybioclip TreeOfLifeClassifier, which is supported for that checkpoint.
- Model downloads and taxonomy resources use the Aperture-owned Hugging Face cache.
- The harmless Windows symlink cache warning is suppressed without requiring elevation or Developer Mode.
- Canonical results retain the selected model, runtime and taxonomy-embedding provenance.
- The legacy BioCLIP suggestion screen no longer labels its separate historical model as the current capability model.

## Compatibility

No schema migration is included. Build 33.1 remains a clean-start field-test release.
