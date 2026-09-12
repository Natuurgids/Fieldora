# Facility floorplan integration boundary

The reusable floorplan UI intentionally lives in `natureai_next.ui.qt.facility_floorplan` rather than inside `v5_desktop.py`. This keeps the already-large desktop composition file from accumulating drawing/rendering logic.

`FacilityFloorplanDialog` requires only an `OperationsAssetService`, actor id and optional drawing/location id. The V5 Operations workspace can therefore wire it from the existing `AssetEquipmentOperations._open_drawing` and facility-selection actions without exposing SQL or duplicating hierarchy logic.

The desired desktop integration is:

- `Open drawing` -> `FacilityFloorplanDialog(service, actor=..., drawing_id=...)`;
- `Show location drawing` -> resolve `location_drawing_context(...)`, open dialog and highlight the location;
- future-layout tab -> same canvas with the planned revision selected plus planned-placement overlays;
- relocation tab -> `placement_picklist(...)`, campaign steps and step-state actions.

This separation also makes the same canvas reusable from future collection-management, laboratory and warehouse workspaces as long as those resources resolve to canonical Operations locations.
