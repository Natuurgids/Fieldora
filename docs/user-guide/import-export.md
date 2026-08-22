# Import and Export Guide

## Import

- **Managed:** copy originals into the library-managed storage.
- **Linked:** retain originals at their current paths.
- **Hybrid:** combine both approaches under one library.

Review the scan summary and duplicate policy before starting. Do not disconnect linked storage or removable media during active work. Failed items can be inspected without discarding successful imports.

## Export

Exports may contain originals, selected derivatives, and JSON/CSV metadata. Validate naming templates and destination capacity first. Export never changes source-library records or original photographs. Interrupted resumable exports can continue through Activity Center where supported.


## GBIF archive roles

A GBIF Darwin Core Archive can be used in two different workflows. **Imports** extracts supported embedded photographs for the media library. **Taxonomy Resources** reads the archive core table as taxonomy and installs names separately from AI model packages. External media URLs are not downloaded automatically in either workflow.

## Export packages with originals

A report or data export may include selected original photos, sounds, videos, and documents. The default policy continues when an original is offline or missing and records the condition in `manifest.json`. Strict mode requires every selected original and leaves no partial destination when validation fails. Originals may also be excluded while keeping report, data, preview, and summary files.
