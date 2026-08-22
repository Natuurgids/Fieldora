# Facility floorplan feature status

Current branch: `feature/versioned-facility-floorplans`

Implemented in the branch:

- canonical Operations location hierarchy remains authoritative;
- version/status aware building drawing revisions;
- source Library asset and operational SVG links;
- normalized point/rectangle/polygon/polyline geometry linked to locations/assets;
- location-to-drawing and drawing-to-location service navigation;
- future layout and relocation data model;
- reliable `FacilityPlanningService` facade for planned placement and relocation generation;
- all new planning/mobile/UI callers use `FacilityPlanningService`, not the older duplicate planning helpers on `OperationsAssetService`;
- reusable Qt `FloorplanCanvas` and `FacilityFloorplanDialog`;
- reusable `FacilityPlanningWorkspace` for floorplans, future layouts, picklists and relocation execution;
- V5 `AssetEquipmentOperations` runtime integration without replacing the existing asset/maintenance/calibration page;
- V5 **Open drawing** now opens the interactive floorplan rather than an external file;
- V5 **Map locations on floorplan** replaces manual X/Y marker entry;
- V5 **Show location drawing** is available from both Operations assets and Facilities & storage selections;
- V5 **Add drawing** is Library-first: preserved/searchable Library drawing assets become Operations drawing revisions;
- additional Library source/reference drawings and Library SVG operational floorplans can be linked to a revision;
- mobile/server relocation contract with guarded state transitions and destination floorplan geometry;
- focused GitHub Actions workflow for Ruff plus facility/versioning/planning/mobile tests;
- regression coverage for revisions, geometry, migration, source links, Library bridge, planning, relocation, mobile transitions and lazy V5 integration.

Release invariants:

1. The Facilities & Storage hierarchy is authoritative; SVG geometry represents it and never replaces it.
2. A future layout does not mutate current physical placement.
3. Intermediate relocation states (`removed`, `in_transit`, `staging`) do not change the canonical live location.
4. Final placement states (`stored`, `placed`, `displayed`, `completed`) may update the live location and append movement history.
5. Original design/source drawings remain governed Library assets; the operational SVG is a separately versioned spatial representation.
6. Until the duplicate base helpers are reconciled, future-layout creation and relocation generation must enter through `FacilityPlanningService`.

Still required before merge/release:

- obtain a successful run of the focused facility certification workflow;
- run the broader Fieldora Ruff/unit/migration/Qt certification suite against the branch;
- perform an interactive desktop smoke test with real SVG/PDF/CAD-derived Library assets and a multi-level location hierarchy;
- review and wire server HTTP exposure for the `FacilityMobileService` contract before the mobile client consumes it;
- reconcile/fix the older planning helper implementations still present directly on `OperationsAssetService` in a controlled whole-file cleanup/refactor, without risking unrelated Operations code.

Keep the pull request in draft until the certification evidence is green.
