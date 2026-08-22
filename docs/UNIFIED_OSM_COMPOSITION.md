# Unified OpenStreetMap Composition

Aperture stores regional OpenStreetMap downloads independently but renders them as one continuous logical map.

## Request flow

1. MapLibre requests one XYZ vector tile.
2. Aperture finds every enabled package whose declared geographic envelope intersects the tile.
3. Each matching MBTiles database is opened read-only.
4. Same-named MVT layers are merged. Feature tag key/value indexes are remapped into the combined layer dictionaries.
5. The merged tile is returned from the loopback-only endpoint.

Package boundaries remain relevant to download, update, verification, and removal. They do not define normal navigation. Missing coverage produces an empty tile; it never causes a distant regional package to be substituted.

## Concurrency and ownership

Tile requests are handled concurrently by the loopback server. Source databases are read-only. Any future derived composite cache uses one writer queue and many independent readers/generators. Source packages remain the recoverable data; composite tiles are disposable derived artifacts.
