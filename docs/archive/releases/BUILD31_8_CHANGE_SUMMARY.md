# Build 31.8 Change Summary

- Added an optional inference snapshot root to local BioCLIP suggestion generation.
- Persisted an atomic JPEG of the center-cropped and resized BioCLIP input per inference run and asset.
- Stored the relative snapshot path and dimensions in immutable suggestion provenance.
- Resolved snapshot paths relative to the active Aperture Library in the AI Review repository.
- Added **Image used for this rating** to the AI Review explanation panel.
- Older inference records remain readable and show a clear regeneration message when no snapshot was retained.
