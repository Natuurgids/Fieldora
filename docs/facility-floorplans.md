# Facility floorplans and relocations

Fieldora treats the existing Operations location hierarchy as the source of truth for physical placement. Floorplans are visual representations of those canonical location records; they do not create a second hierarchy.

## Drawing revisions

`ops_building_drawings` stores drawing revisions and distinguishes draft, planned, approved, scheduled, current, superseded and archived material. Source/design files may remain preserved in the Library while an operational SVG is linked for interactive use. Activating a revision supersedes the previous current revision for the same location without deleting it.

## Interactive geometry

`ops_drawing_markers` stores normalized point, rectangle, polygon or polyline geometry linked to an existing location or operations asset. Normalized coordinates keep geometry independent of screen resolution and make SVG replacement practical when revisions retain the same coordinate model.

The desktop floorplan canvas can browse revisions, click mapped locations, highlight a selected location and draw a polygon for a canonical location. Geometry is persisted through `OperationsAssetService`; the UI does not issue SQL directly.

## Current versus future placement

Future layouts are stored in `ops_layout_plans` and `ops_planned_placements`. Planning a placement does **not** change the resource's live `location_id`. A relocation campaign turns an approved plan into ordered work steps. Only a completed physical placement executes the canonical movement.

This separation allows Fieldora to show today's floorplan and a future arrangement side by side, prepare pick lists, stage moves and preserve movement history.

## Source material and Library links

A drawing may link to preserved source material through `library_asset_id`, `operational_svg_asset_id` and `ops_drawing_sources`. Typical relationships include source PDF/CAD files, an operational SVG derivative, reference images and later as-built revisions. The source evidence remains a Library concern while Operations owns the version/status and physical-location interpretation.

## Intended workflow

1. Create or select canonical institution/site/building/floor/room/storage locations.
2. Add a drawing revision and link the source Library asset.
3. Link or generate an operational SVG.
4. Draw polygons or other normalized geometry for existing locations.
5. Activate the approved revision when it becomes current.
6. Create a future layout and planned placements without changing live positions.
7. Generate a relocation campaign, execute its steps and record physical movement.
8. Retain superseded plans and movement history for audit and reconstruction.
