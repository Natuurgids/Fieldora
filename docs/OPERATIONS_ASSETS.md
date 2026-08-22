# Asset, Equipment & Facilities Operations

This clean-install module manages maintainable/calibratable assets and physical storage. Locations are hierarchical and can represent institutions, sites, buildings, floors, wings, halls, rooms, zones, cabinets, freezers, racks, drawers, shelves, boxes, trays and parts. Assets reference stable location IDs; the UI renders the complete location path.

Building drawings preserve original Visio, EdrawMax, BIM/IFC, CAD, PDF, SVG or raster files. Drawing markers associate coordinates with a location or asset code. Storage conditions can be defined at any hierarchy level.

The SQLite schema is created by `OperationsAssetService`. Equivalent PostgreSQL tables are created by `PostgresOperationsSchema`. This release is clean-install only and contains no migration path.
