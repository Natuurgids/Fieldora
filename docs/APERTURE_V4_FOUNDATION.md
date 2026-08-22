# Aperture V4 Foundation — 4.0.0.dev1

This increment establishes the executable ownership boundary for Aperture V4.

## Ownership rule

Aperture owns canonical enrichment, review decisions, subject projection and source snapshots. SynthesisCore executes replaceable offline capabilities and returns stable `CapabilityResult` values. SynthesisCore does not import or manipulate Aperture database adapters.

## Implemented flow

1. A capability receives a `CapabilityRequest`.
2. It returns a producer-neutral `CapabilityResult` containing canonical candidates.
3. `CapabilityTranslationService` validates and stores each candidate as `pending_review`.
4. `CanonicalEnrichmentService` accepts or rejects the same record from any workspace.
5. `EnrichmentProjectionService` projects canonical records into photo, sound, video, document or observation views.
6. `SourceRegistryService` can deactivate or remove a source while preserving accepted enrichment by default.

## Canonical shapes

The stable V4 contract includes label, taxonomy candidate, bounding box, segmentation, time segment, time-frequency region, transcript segment, document region, measurement, relationship and artifact reference.

## Extension manifest V2

Manifests remain backward compatible. New optional fields describe extension kind, input kinds, output shapes, parameters, offline bundle files, checksums and attribution. `kind` supports `capability` and `source`.

## Schema additions

The isolated enrichment database now stores source records, source snapshots, review timestamps and review history. Fresh V4 databases accept photo, sound, video and document subjects and the complete V4 review lifecycle.

## Current limitation

This increment provides the domain, persistence, execution-boundary and projection foundation. Existing BioCLIP UI and worker integration have not yet been routed through the new translation service. Generic UI renderers, retention profiles and source package file deletion are planned for subsequent increments.
