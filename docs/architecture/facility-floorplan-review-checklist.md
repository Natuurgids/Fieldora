# Facility floorplan review checklist

Before merge:

- schema upgrades succeed on a pre-feature Operations database;
- new floorplan geometry is normalized and linked to canonical locations;
- current drawing activation preserves superseded revisions;
- operational SVG source remains distinct from preserved Library evidence;
- planning a future placement never changes the live asset location;
- relocation completion changes live placement exactly once and records movement history;
- duplicate scanner submissions are idempotent;
- Qt viewer opens current/planned revisions and highlights a location from the Facilities list;
- polygon drawing saves through `OperationsAssetService` only;
- source drawing and generated SVG links can be reached from Library/Operations;
- CI, migration tests and GUI import guards are green.
