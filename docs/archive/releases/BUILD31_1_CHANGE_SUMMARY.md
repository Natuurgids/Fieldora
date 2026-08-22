# Build 31.1 Change Summary

Build 31.1 repairs field regressions in the Build 31 photo workflow.

## Viewer

The Viewer now resolves the newest valid preview derivative, then the thumbnail derivative, before decoding the linked or managed original on its dedicated worker thread. The Qt event loop is never used for image decoding.

The Viewer/Enrichment splitter uses a 70/30 ratio and the enrichment panel is capped at 30 percent of the dialog width.

## Gallery thumbnails

Visible thumbnail workers re-query the catalog for the newest valid derivative path. This allows thumbnails completed after the catalog page was loaded to appear without regenerating originals during scrolling. Gallery requests remain cache-only.

## Validation

The regression suite includes explicit tests for cache-only gallery behavior, Viewer original fallback, derivative re-resolution, and the 70/30 layout contract.
