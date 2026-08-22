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
- HTTP-neutral `FacilityApiAdapter` for authenticated server delegation;
- focused GitHub Actions workflow for Ruff plus facility/versioning/planning/mobile/server tests;
- separate facility migration and offscreen Qt/V5 certification gates;
- regression coverage for revisions, geometry, migration, source links, Library bridge, planning, relocation, mobile transitions, server adapter and lazy V5 integration.

Certification evidence:

- focused workflow run `32587004864` reached the runtime suite after all Ruff stages passed; 15 tests passed and the only two failures were missing Ubuntu `libEGL.so.1` dependencies for PySide6;
- the workflow was corrected to install the required Qt runtime libraries rather than changing application code;
- corrected focused workflow run `32587069658`, on commit `956e7bc77463a8a996c6279451ab2348709e99a4`, completed successfully: Qt setup, all focused Ruff stages and the complete facility unit/migration suite passed;
- current focused facility certification run `32591991219` passed;
- current offscreen Qt/V5 certification run `32591991239` passed;
- current facility schema-upgrade/compatibility certification run `32591991339` passed;
- a repository-wide unit comparison was run without forcing a facility administrator identity. The feature branch produced `745 passed / 5 failed`; `main` produced `728 passed / 5 failed`. The five failures are identical and are pre-existing Measurements/Qt/static-navigation failures, so this feature introduces no additional broad unit-test failures;
- strict full-repository Ruff was also exercised. It reports existing lint debt across unrelated `main` modules in addition to the two known facility-branch exceptions. The feature-specific remaining Ruff debt is the `UP035` import in the large shared `OperationsAssetService` module plus import ordering/two unused imports in `facility_planning.py`.

Release invariants:

1. The Facilities & Storage hierarchy is authoritative; SVG geometry represents it and never replaces it.
2. A future layout does not mutate current physical placement.
3. Intermediate relocation states (`removed`, `in_transit`, `staging`) do not change the canonical live location.
4. Final placement states (`stored`, `placed`, `displayed`, `completed`) may update the live location and append movement history.
5. Original design/source drawings remain governed Library assets; the operational SVG is a separately versioned spatial representation.
6. Until the duplicate base helpers are reconciled, future-layout creation and relocation generation must enter through `FacilityPlanningService`.

Still required before merge/release:

- perform an interactive desktop smoke test with real SVG/PDF/CAD-derived Library assets and a multi-level location hierarchy;
- wire the HTTP-neutral `FacilityApiAdapter` into the main authenticated server composition before the mobile client consumes it, preserving the existing single authentication/tenant-quota path;
- reconcile/fix the older planning helper implementations still present directly on `OperationsAssetService` in a controlled whole-file cleanup/refactor, without risking unrelated Operations code;
- remove the two narrow focused-CI import-rule exceptions (`UP035` for the large shared Operations service and `I001/F401` for the planning UI) during that controlled cleanup;
- decide separately whether the pre-existing repository-wide Ruff and five broad-unit baseline failures are release blockers for Fieldora as a whole; they are not regressions introduced by this facility branch.

Keep the pull request in draft until the authenticated server composition and interactive smoke evidence are complete.
