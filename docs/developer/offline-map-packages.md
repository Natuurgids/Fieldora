# Offline Map Catalogs and Bundles

## Catalogs

An Aperture map catalog is a JSON hierarchy. Navigational entries may represent continents, countries, states, regions, or provinces. Downloadable entries must provide:

- a stable `entry_id`;
- `downloadable: true`;
- `format: mbtiles`;
- an HTTPS `download_url`;
- a 64-character SHA-256 value;
- package version, bounds, zoom range, licence, and attribution where available.

The provider defines the administrative hierarchy. Aperture does not assume that every country has the same levels.

## Aperture map bundles

A map bundle uses the `.apkg` extension and is a ZIP archive with this structure:

```text
bundle.json
packages/<package>.mbtiles
```

`bundle.json` must declare:

```json
{
  "bundle_format": "aperture-map-bundle",
  "schema_version": 1,
  "name": "Prepared field maps",
  "packages": [
    {
      "entry_id": "stable-package-id",
      "name": "Region name",
      "region_type": "province",
      "package_version": "2026.07",
      "package_path": "packages/region.mbtiles",
      "sha256": "...",
      "bounds": [4.0, 50.0, 6.0, 52.0]
    }
  ]
}
```

Bundle paths must be relative and must not contain parent traversal. Every embedded file is extracted to a private temporary directory, hashed, structurally validated as MBTiles, and atomically moved into Aperture-managed storage before activation.

## Operational rules

- Never point catalogs at public OpenStreetMap tile endpoints for bulk acquisition.
- Regenerate checksums after producing final MBTiles files.
- Package replacement is atomic: the existing package remains usable until the replacement verifies.
- Catalog or bundle failure must not affect the core Aperture Library.

## Vector renderer prototype gate

The renderer probe loads `PySide6.QtWebEngineWidgets` only when vector-package capabilities are requested. It then requires pinned `maplibre-gl.js`, `maplibre-gl.css`, and `pmtiles.js` assets plus an Aperture-owned range-capable archive bridge. A developer prototype may point `APERTURE_VECTOR_RENDERER_ASSETS` at an asset directory, but that does not approve or package those files and cannot make a package renderable without the archive bridge.

The archive-reader port accepts only an installed package public ID, byte offset, and length. Its Infrastructure adapter supports PMTiles, requires an enabled installed catalog record, checks the verified file size, and limits each request to 8 MiB. It deliberately does not accept a path from JavaScript or expose a localhost endpoint. The later browser scheme adapter must translate browser range requests onto this port.

Application accepts only a single explicit browser range in the form `bytes=start-end`. It returns partial-content metadata and the bounded archive slice. Missing, open-ended, suffix, reversed, malformed, and multi-range requests are rejected before the reader is called. The Qt scheme adapter must remain a thin translation layer around this service.

The Qt adapter reserves `aperture-map://<package-id>/archive`. It imports WebEngine lazily, permits only GET, forwards the Range header, adds partial-content headers, and owns the reply buffer for the request lifetime. Bootstrap must register the scheme before creating a WebEngine profile and install the handler only for the map renderer profile.

Renderer assets require `renderer-assets.json` schema 1 with `approval_status: approved`. The manifest must contain exactly `maplibre-gl.js`, `maplibre-gl.css`, and `pmtiles.js`; every entry requires a pinned version, licence identifier, and SHA-256. Verification occurs before archive-bridge or renderer readiness is reported.

Street packages must declare `schema: aperture-streets-v1`, layers `landuse`, `water`, `building`, `transportation`, and `place`, label fields `transportation.name` and `place.name`, generated base zoom 14 or deeper, attribution, and a data licence. MapLibre supplies higher interactive zoom through vector overzoom. A structurally valid archive without this metadata remains installed but is not renderer-compatible.


## Geofabrik OpenStreetMap provider

Aperture uses the official Geofabrik region index as its default online map source. An internet connection is required to retrieve the catalog and selected regional extract. Only leaf regions offered by the provider are downloadable in the normal interface. NatureAI Next verifies the provider file when a checksum sidecar is available, converts the regional shapefile extract locally into raster MBTiles, and registers the finished package with Aperture. Installed maps then work without a network connection. Public OpenStreetMap tile servers are never bulk-downloaded.

Build 3 treats this zoom-10 raster generator as a compatibility provider. ADR-032 directs new street-level coverage toward regional vector-tile containers behind the existing provider ports. Bootstrap must compose the setup platform, renderer, and converter; Qt must not import concrete map adapters or rely on Maintenance Center module state.

The MapLibre GL JS/PMTiles renderer remains an isolated prototype. The official tilemaker 3.0.0 Windows executable is packaged behind the converter port with pinned archive and executable checksums. The combined path remains pre-commercial until field validation proves base zoom 14 plus street-level overzoom, labels, overlays, rotation, offline restart, resource bounds, licensing, and compatibility with the command installers.

The completion candidate activates a conforming PMTiles archive only when WebEngine, approved assets, the private range bridge, package integrity, and `aperture-streets-v1` metadata all pass. Internal catalog IDs are encoded into canonical Base32 private authorities and decoded inside the scheme handler; the renderer never receives a filesystem path. Interactive viewport changes trigger new bounded spatial projections for photo, observation, site, temporal-track, and GPX overlays.

Build 3.41–3.50 introduces explicit container compatibility ahead of that renderer. Catalog format `vector-mbtiles` requires MBTiles metadata format `pbf` or `mvt`; catalog format `pmtiles` requires a PMTiles v3 header. Both require catalog SHA-256 verification. A valid vector archive is installed and inventoried with the state **Installed — vector renderer pending** and is never passed to the raster tile decoder.

Build 3.61–3.70 adds the renderer-readiness contract. The Infrastructure query adapter maps each installed package to a Domain capability projection containing format, readiness, renderer key, status, message, and maximum zoom. Application exposes the projection; Qt does not inspect SQLite metadata or select renderer adapters.

## Activity scheduling and database integrity

Offline-map catalog entries are submitted individually to the application-wide Activity Center. The Activity Center maintains durable queued/running states and applies a bounded concurrency budget for `offline-map.prepare` activities. This provides parallel network and conversion work without launching one `QThread` per selected region simultaneously. Queued activities are promoted oldest-first when a worker slot becomes available.

The map acquisition service continues to prepare and validate packages before the short catalog-registration phase. Existing atomic replacement, verification, recovery, cancellation, and retry behavior is unchanged. SQLite-backed installed-package views are not refreshed for ordinary progress events. They are coalesced and refreshed after terminal map activity transitions, so worker progress cannot cause repeated synchronous database reads and widget rebuilds on the Qt event thread.

The concurrency limit is deliberately owned by the Activity Center rather than the Offline Maps dialog. This keeps menu actions modular and allows later activity kinds to declare their own safe worker budgets while preserving subsystem database ownership.

## Adjacent-package rendering

The raster workspace queries every enabled renderable MBTiles package valid for the active zoom. For each tile center, it selects the first package whose geographic bounds cover that coordinate and that can return the tile. Packages covering the current viewport center retain priority, preserving existing behavior while allowing adjacent package composition.

### Composite vector packages

All-mode vector rendering uses one loopback MapLibre origin backed by an ordered set of read-only MBTiles packages. Each tile request is checked against package bounds and zoom limits and falls through until a package supplies the tile. This preserves same-origin worker behavior while allowing adjacent regional extracts to form one continuous canvas.
