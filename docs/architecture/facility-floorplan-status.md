# Facility floorplan feature status

Current branch: `feature/versioned-facility-floorplans`

Implemented in the branch:

- canonical Operations location hierarchy remains authoritative;
- version/status aware building drawing revisions;
- source Library asset and operational SVG links;
- normalized point/rectangle/polygon/polyline geometry linked to locations/assets;
- location-to-drawing and drawing-to-location service navigation;
- future layout and relocation data model;
- reusable Qt `FloorplanCanvas` and `FacilityFloorplanDialog`;
- regression coverage for revisions, geometry, source links and GUI module import.

Still to integrate before release:

- replace the V5 Operations drawing `Open drawing` action with `FacilityFloorplanDialog`;
- add explicit current/future layout management tabs to the Operations workspace;
- add pick-list and relocation execution UI;
- add server/mobile adapters for relocation step scanning;
- validate layout/relocation SQL workflows in CI and correct any migration defects before merge;
- complete Library relationship affordances for source drawings and generated operational SVG assets.

Do not merge this branch until CI and the relocation workflow tests are green.
