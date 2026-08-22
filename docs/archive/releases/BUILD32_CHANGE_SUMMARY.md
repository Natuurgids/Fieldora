# Build 32 Change Summary

## Multimodal Knowledge Review

Build 32 changes Knowledge Base from a BioCLIP-specific review destination into a media-aware AI review hub.

The new AI Review workspace exposes:

- Overview
- Photos
- Sounds
- Videos
- Documents
- Comparisons
- Accepted Knowledge

Photo review retains the proven BioCLIP workflow, keyboard controls, immutable suggestion provenance, persisted model-input image, and taxonomy decisions. Sound, video, and document tabs define the approved evidence-specific review boundaries without pretending unsupported review data exists.

## Capability-scoped model activation

The Models workspace now explains the existing multi-model behavior correctly. Activating a model enables it only for compatible media capabilities. Several models may remain active when they serve different media or enrichment types.

Each model card now reports:

- compatible media and enrichment capability;
- review mode;
- Library workspace from which enrichment is launched;
- installation and dependency state.

## Generation model versus result provenance

Photo AI Review now distinguishes:

- the current model used for new photo generation;
- the exact model, variant, provider, prompt set, precision, and preprocessing recorded on the selected historical suggestion.

Changing an active model never rewrites the provenance of an existing suggestion.

## Execution boundaries

Build 32 does not centralize media execution. Photos, sounds, videos, and documents continue to start enrichment from their own Library workspaces and retain independent workers, queues, resource classes, and storage. Knowledge Base is the shared review and interpretation surface.
