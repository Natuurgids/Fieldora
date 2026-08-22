
### Knowledge Base read scheduling

`KnowledgeDataView` must never open or query SQLite from the Qt GUI thread. Each refresh captures the current search/provider/state filters and runs them on a thread-confined read-only connection (`mode=ro`, `query_only=ON`). The GUI thread only applies the completed row projection. While a query is active, further refresh requests are coalesced into one follow-up query using the latest widget state. Workspace construction is side-effect free: loading begins only when the Knowledge Base or its active tab is activated.

Completed query projections are rendered in bounded batches rather than one monolithic `QTableWidget` update. This preserves the existing result limits while allowing paint, navigation, and Windows message processing between batches.


## Offline map render ordering (Build 27 Repair 2)

Map presentation uses an explicit foreground contract. Raster tiles and empty-tile placeholders render at z=-100; tracks at z=20; sites at z=30; observations at z=40; media clusters at z=50; cluster labels at z=51; and status/UI annotations at z=100. The vector MapLibre renderer owns stable `aperture-*` source and layer identifiers. On load, `styledata`, and idle transitions it recreates any missing overlay objects and verifies that the ordered Aperture layer stack is the final layer stack in the active style. This prevents offline packages, style reloads, and delayed basemap layers from covering media markers.
