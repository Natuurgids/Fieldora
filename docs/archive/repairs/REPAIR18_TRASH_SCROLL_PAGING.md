# Repair 18: Trash scroll retention and continuous paging

The gallery no longer performs `refresh()` after successful trash or permanent deletion. The database maintenance result is applied to the current `_GalleryModel` through contiguous `beginRemoveRows()` / `endRemoveRows()` ranges. The model instance, loaded pages, `_next_cursor`, filters, and sort context remain intact.

The scrollbar now drives both viewport thumbnail scheduling and a guarded near-bottom paging check. A deferred paging check runs after page insertion and row removal so an underfilled viewport continues loading. `_refreshing` prevents duplicate page workers.

Thumbnail inputs, queued jobs, failures, in-flight bookkeeping, and completed state are removed only for affected public IDs.
