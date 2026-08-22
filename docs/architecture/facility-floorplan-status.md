# Facility floorplan implementation status

Current branch: `feature/versioned-facility-floorplans`

## Implemented

- Existing `ops_locations` hierarchy remains the canonical physical-location model.
- Building drawings support revision lifecycle states including draft, planned, approved, scheduled, current, superseded and archived.
- Operational floorplans can reference a managed SVG while original design/reference documents remain separate.
- Drawings and operational SVGs can reference governed Library asset IDs; Operations does not introduce a second document repository.
- Floorplan geometry supports normalized point, rectangle, polygon and polyline representations linked to existing locations/assets.
- Location -> drawing and drawing -> mapped-location queries are available through the Operations service.
- `FacilityFloorplanDialog` and `FloorplanCanvas` provide an interactive Qt viewer/editor with location highlighting and polygon creation.
- `FacilityPlanningService` provides explicit future-placement and relocation creation paths with corrected SQL column/value counts.
- Planned placements do not mutate live asset locations.
- Relocation campaigns generate executable move steps from planned placements.
- Intermediate states such as removed, in-transit and staging preserve the existing live location.
- Final states such as stored, placed, displayed and completed can execute the physical move and append movement history.
- `FacilityPlanningWorkspace` provides floorplan revision controls, future layouts, planned placement, CSV picklists, relocation campaigns and move-state execution as a reusable Qt component.
- `FacilityDrawingLibraryBridge` validates and resolves source/operational drawing Library assets.
- Regression tests cover versioning, geometry, Library references, future planning, non-destructive intermediate movement and final placement.

## Deliberately not merged yet

The feature remains on draft PR #1. The current V5 `AssetEquipmentOperations` page still uses its legacy file-open/manual X-Y marker actions. The new floorplan/planning components are intentionally isolated until their workflow tests are green; the final integration will replace those actions with the interactive dialog/workspace instead of duplicating facilities logic.

## Next integration slice

1. Wire `Open drawing` to `FacilityFloorplanDialog`.
2. Add `Show location drawing` from Facilities & Storage and highlight the selected location.
3. Surface current/planned drawing lifecycle and source-Library relationships in the V5 Operations page.
4. Embed the future-layout/relocation workspace as Operations tabs rather than a parallel application.
5. Add Library asset selection for source drawings and operational SVGs using the existing Library catalogue/import workflow.
6. Expose relocation picklist and state transitions through the server/mobile API boundary.
7. Run Ruff, unit tests, migration tests and Qt smoke tests before taking PR #1 out of draft.
