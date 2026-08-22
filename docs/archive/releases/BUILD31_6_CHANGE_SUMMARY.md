# Build 31.7 Change Summary

## Persistent thumbnail fallback

Build 31.7 compares the current derivative pipeline with the original Build 28.4 Repair 2 implementation. Repair 2 reliably displayed thumbnails because the gallery worker decoded missing originals, but it keyed cache files only by source metadata and did not guarantee a stable per-asset offline path. Build 31.7 keeps the reliable worker-thread behavior and adds a stable Aperture-owned path under `cache/thumbnails/assets/`. The first missing request renders and writes atomically; every later request reads the cached JPEG.

## Trash dependency deletion

Permanent deletion now resolves direct restrictive foreign keys against `assets` from the active SQLite schema. Nullable audit/history references are set to NULL. Non-null dependent records are deleted. Cascading relationships continue to use SQLite's declared cascade rules. All catalog changes are committed in one transaction after managed and derivative file purge.

## Tests

Added runtime tests for one-time stable thumbnail materialization, offline cache reuse, and restrictive foreign-key cleanup. Updated obsolete cache-only assertions to the field-tested persistent fallback contract.
