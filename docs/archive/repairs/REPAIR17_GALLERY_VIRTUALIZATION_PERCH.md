# Repair 17: Gallery virtualization and Perch 2 initialization

## Photos gallery

The Photos workspace now uses Qt Model/View rather than item widgets:

- `QListView` owns selection, scrolling, and a fixed 220 × 240 grid.
- `_GalleryModel`, a `QAbstractListModel`, stores lightweight catalog rows and emits batched `beginInsertRows`/`endInsertRows` notifications when paging.
- `_GalleryDelegate`, a `QStyledItemDelegate`, paints fixed-size thumbnail cells.
- Uniform item sizes, fixed resize mode, and batched layout prevent full-grid relayout when a page is appended.
- Thumbnail requests are created only for the visible viewport plus a one-row margin.
- Queued, in-flight, and completed identity sets deduplicate jobs.
- Existing stable public-id roles preserve filtering, selection, review, metadata, context actions, enrichment, and viewer navigation.

No database migration is required. The page size and query cursor contract are unchanged.

## Perch 2

The Perch catalog now declares `kagglehub` as a required isolated dependency. Both health checking and enrichment call `_initialize_perch2()`, which imports required acquisition dependencies and instantiates `bioacoustics_model_zoo.Perch2()`. A health check therefore cannot pass on import alone. Initialization errors identify the missing module or constructor failure and direct the operator to reinstall Perch dependencies.
