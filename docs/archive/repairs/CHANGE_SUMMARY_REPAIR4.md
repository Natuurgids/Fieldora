# Repair 4 Code Change Summary

## `infrastructure/imaging/catalog_thumbnails.py`

Changed thumbnail loading from synchronous cache-miss rendering to cache-first, background materialization. `load()` now reads existing persistent derivatives only, queues missing work, and returns without decoding the original. Added a bounded executor, duplicate-request coalescing, atomic idempotent `materialize()`, cache-path exposure, and graceful shutdown.

## `application/storage.py`

Extended storage verification so its result is propagated to the corresponding `file_instances.availability_state` and aggregated into `library_assets.availability_state`. This makes Storage Manager state the shared state consumed by catalog table and detail queries.

## `application/storage_transactions.py`

Added a durable SQLite journal for copy and move operations. Each item has an independent lifecycle and idempotency key. Copy uses a temporary destination, SHA-256 verification, and atomic replacement. Move removes the source only after the destination is verified. Failures are recorded per item and do not abort a batch. Pending/failed work can be retried after restart.

## `tests/test_build28_4_repair4_storage_stabilization.py`

Added five stabilization tests for offline thumbnails, queue coalescing, independent batch failures, verified move ordering, and graceful cancellation/recovery.
