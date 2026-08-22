## V3.RC1 integrated NatureAI resources

The default NatureAI classifier uses pybioclip TreeOfLifeClassifier and its matching Tree-of-Life resources. GBIF and custom CSV prompt sets are optional, independent additions.

# Local AI and Resource Guide

Fieldora uses the Fieldora Engine resource registry and package formats. Model, prompt, taxonomy, preprocessing, provider, and application identities are recorded with generated suggestions.

Before inference, confirm that a compatible signed model package, prompt set, and taxonomy resource are active. CUDA is preferred when available; CPU remains the safe fallback. Low-confidence or unknown outcomes are valid results and should not be forced into a taxon.

Photographs stay local. Resource downloads occur only after an explicit user action. Use Health Check to copy diagnostic information when seeking support.


## Interrupted BioCLIP downloads

Build 3.321 stores incomplete official checkpoint downloads as `.part` files and resumes them with HTTP Range requests. Retry does not discard already downloaded bytes. Persistent failures can be bypassed by selecting a locally downloaded checkpoint in BioCLIP Quick Setup. Taxonomy resources are installed independently under **Taxonomy Resources** and are reconciled with BioCLIP through taxonomy embeddings.

## Responsive AI Review loading

AI Review opens immediately and shows a loading message while Fieldora retrieves model status, queue counts, and the first page of suggestions in the background. Selecting a suggestion also loads its evidence, personal observation context, ecology, and enrichment history without blocking the rest of the application. Changing filters during a load is safe: Fieldora finishes the active query and then applies the newest requested filter.
