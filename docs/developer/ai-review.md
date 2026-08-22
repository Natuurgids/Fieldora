# AI Review

## GUI-thread boundary

AI Review database and provider reads must not execute in Qt event handlers. `AIReviewWorkspace` uses thread-confined refresh and detail workers for overview, page, detail, regional evidence, observation context, ecology, and enrichment reads. Worker results are immutable application/domain objects and are rendered only after delivery to the GUI thread. Concurrent refresh requests are coalesced rather than starting unbounded threads. Review mutations remain routed through the existing application service and preserve current transaction semantics.
