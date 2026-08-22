## Build 3.323 map build and rendering behavior

Aperture serializes the Planetiler phase that uses shared Natural Earth, water-polygon, and tile-weight inputs. Multiple requested regions may remain queued, but only one process at a time may prepare or use those shared files. This prevents Windows `NoSuchFileException` failures involving `water-polygons-split-3857.zip_inprogress`. Completed PMTiles packages are opened directly by the renderer, which reads archive metadata before creating the MapLibre source. Any archive, tile, or style error is shown on the map surface.

# Managing Offline Maps

Aperture displays maps entirely from locally installed map packages. The Map workspace does not download tiles while it is being used.

## Prepare maps before field work

Use **Maintenance Center → Manage Offline Maps** before travelling. Load a configured Aperture map catalog, then browse its hierarchy from continent to country and onward to the provider-defined regional unit. The usual lowest downloadable unit is a province, state, department, county, or comparable region.

Download only the coverage needed for the next field period. Regional increments are easier to verify, continue after interruption, update, and remove. Very large selections consume both installation storage and temporary verification space.

Before a download starts, Aperture shows:

- download size;
- estimated installed size;
- temporary working space;
- free space on the map-package drive.

A large-package warning recommends using smaller regional increments. It is guidance, not a restriction.

## Import a complete map bundle

When a complete prebuilt collection is available, use **Import Map Bundle** instead of downloading its regions individually. Aperture accepts `.apkg` map bundles containing:

- `bundle.json`;
- one or more MBTiles files;
- a SHA-256 checksum and package metadata for every file.

Aperture verifies every package before registration. Invalid, incomplete, unsafe, or checksum-mismatched bundle contents are not activated.

A bundle can be copied by USB drive or other offline media. Importing a bundle never contacts a public map server.

## Import an OpenSeaMap nautical overlay

Choose **Import OpenSeaMap Overlay…** to install a prepared transparent raster
MBTiles database containing OpenSeaMap seamarks. Fieldora validates the MBTiles
schema, bounds, zoom range and PNG/WebP tile format, calculates a SHA-256
checksum, copies the database into managed offline-map storage, and records its
source, attribution, licence and reference-only navigation status.

The import runs in Activity Center. The Offline Maps window may be closed while
verification and copying continue. Fieldora does not bulk-download the public
OpenSeaMap raster tile service.

An enabled nautical package is composed automatically over compatible raster or
vector offline basemaps and can be disabled independently from the installed
package table. It is also identified from the Marine & Freshwater Science and
Maritime Operations workspaces.

> OpenSeaMap layers in Fieldora are scientific and operational reference
> material. They are not certified electronic navigational charts and must not
> be used as the sole source for navigation.

## Updates, enablement, and removal

Installed packages can be enabled, disabled, replaced by a verified newer package, or removed to recover space. Removing a basemap package does not remove:

- photo GPS coordinates;
- observation locations;
- monitoring sites;
- saved scientific regions;
- movement history.

If no enabled package covers the current view, Aperture keeps the Map workspace available and reports that offline map coverage is unavailable.

For an installed vector MBTiles or PMTiles package, **Map engine** reports the first unavailable renderer prerequisite. The gate distinguishes the Qt WebEngine runtime, approved renderer assets, local archive access, package schema, and package integrity. A conforming PMTiles package is opened automatically when all gates pass. Build 3.321 uses a fully local, glyph-independent style so roads, water, land use, and buildings render even when no label font pack is installed. Street labels are intentionally omitted until an approved bundled glyph pack is available. Any MapLibre style or tile-source error is shown directly on the map.

## Map source policy

Aperture does not create offline archives by bulk-downloading from public
OpenStreetMap or OpenSeaMap tile servers. Catalogs, bundles and nautical imports
must provide licensed, prebuilt Aperture-compatible MBTiles packages with
checksums, attribution and licence metadata.


## Geofabrik OpenStreetMap provider

Aperture uses the official Geofabrik region index as its default online map source. An internet connection is required to retrieve the catalog and selected regional `.osm.pbf` extract. Only leaf regions offered by the provider are downloadable in the normal interface. Aperture verifies the provider file when a checksum sidecar is available, converts it locally into PMTiles through base zoom 14, and registers the finished package. MapLibre overzooms the vector data for street-level interaction. Installed maps then work without a network connection.

The raster package path is retained only for compatibility. Existing raster packages remain usable and do not need to be removed.

New Geofabrik selections use `.osm.pbf` vector input and require the verified Aperture vector converter toolchain before download begins. Aperture no longer silently prepares a new zoom-10 raster map when street-level output was requested. Existing raster packages remain available as compatibility maps.

## Build 3 field validation

Validate both routes before approving the increment:

1. In Aperture, open **Resources → Offline Maps → Open Offline Map Setup…**.
2. In Maintenance Center, open **Offline Maps**.
3. Download or reuse the region catalog, filter to a continent/country, and tick one downloadable leaf region.
4. Choose **Download / Update Selected** and confirm that Activity Center immediately shows a running preparation with visible download progress.
5. Cancel once, then use Resume / Retry and confirm that the partial download is reused safely.
6. Confirm verification, conversion, registration, enablement, and offline reopening of the installed region.
7. Open Maps, choose the new Area, and verify roads, buildings, water, road/place labels, attribution, pan, zoom through 18, compass rotation, cursor coordinates, and marker details.
8. Pan away and back; confirm photo, observation, monitoring-site, and temporal overlays follow the current viewport.
9. Open a representative GPX 1.0/1.1 track, verify its orange line, then clear it without changing the source file.
10. Restart without networking and confirm the map, overlays, navigation, and attribution remain available.
11. Update or remove a test region and confirm superseded/partial package files are cleaned without removing Library coordinates or observations.
12. Confirm existing raster packages, Library photographs, AI Review, BioCLIP, CMD repair, and uninstall remain available.

Street-level approval is a separate gate: the packaged vector prototype must show readable roads and labels from base zoom 14 through higher renderer overzoom, local overlays, pan/zoom/rotation, attribution, bounded storage/memory, and a clean restart with networking disabled.

Vector MBTiles and PMTiles v3 packages appear as ready only when their format, checksum, street schema, renderer assets, WebEngine runtime, and private archive bridge all pass. A blocked package remains managed and reports the exact missing gate without being misreported as damaged raster data.

The Map workspace shows a **Map engine** readiness summary. Ready raster and vector packages appear in the Area selector; blocked packages remain visible in Maintenance with a specific diagnostic.

## Background preparation and progress

Selected regions are queued as separate background activities. You can close the Offline Maps window and continue using Aperture. Open **Activity Center** to see the current phase, download speed, bytes transferred, rendered tile count, completion, cancellation, or retry. Progress is refreshed once per second to avoid slowing the transfer or map creation.

### Activity Center scheduling and responsiveness

Offline-map preparation uses the existing Activity Center with a bounded worker budget. Selected regions remain separate durable activities, but only a system-appropriate subset runs at the same time; the remainder stay visibly queued and start automatically as workers finish. Cancellation of queued work does not create a worker.

Download, checksum verification, extraction, and vector conversion remain background work. The Activity Center continues to report each activity independently. The installed-map table is refreshed only when an offline-map activity reaches a terminal state, rather than on every progress notification. This prevents large batches from flooding the GUI event queue while preserving progress, cancellation, retry, atomic package publication, and independent map databases.


## Viewing installed areas

The Maps workspace lists enabled installed map packages in the **Area** selector. Choose an area and select **Zoom to Area** to center the viewer on its stored coverage. When the current view has no coverage, opening or explicitly refreshing Maps centers on the first enabled installed area. Pan and zoom remain available, and locations outside downloaded coverage show a clear offline-coverage message.

Vector maps provide mouse and control-button pan/zoom, compass rotation, live cursor coordinates, and a legend. Photographs, observations, and monitoring sites use distinct markers; selecting a marker shows its label. Temporal trails and GPX tracks are drawn as lines. Use **Open GPX Track…** to display a bounded GPX 1.0/1.1 file for the current session and **Clear Track** to remove it from the view without modifying the source file.

## Continuous map view

Downloaded raster maps are shown as one geographic canvas. When neighboring packages are installed, their tiles appear beside the current package. Drag the map toward an adjacent area and release to recenter and load the next surrounding maps. Selecting an Area still centers the view on that package; it no longer restricts the canvas to that file. Empty regions indicate that no eligible offline package covers the requested tile.

### Continuous vector coverage

Choose **All** to combine every compatible installed vector MBTiles region in one map. Aperture resolves each requested vector tile against the installed packages whose bounds and zoom range cover that tile. Choose a named area to restrict rendering to that package only.
