from __future__ import annotations

import json
import zipfile
from pathlib import Path

from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.source_workspace import SourceWorkspaceService
from natureai_next.domain.enrichment import SubjectRef, SubjectType
from natureai_next.infrastructure.subsystems.enrichment import enrichment_descriptor
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.synthesis_core import (
    GeoJsonReferenceImporter,
    GtfsReferenceImporter,
    InProcessSourceRouter,
    RailMlReferenceImporter,
    create_builtin_source_router,
)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "enrichment.sqlite3"
    SubsystemDatabaseRegistry((enrichment_descriptor(path),), "4.0.0.dev1").activate("enrichment")
    return path


def test_geojson_importer_normalizes_spatial_bounds(tmp_path: Path) -> None:
    database = _database(tmp_path)
    source = tmp_path / "regions.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "area-1",
                        "properties": {"name": "Wetland"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[4.0, 51.0], [5.0, 51.0], [5.0, 52.0], [4.0, 51.0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    router = InProcessSourceRouter()
    router.register(GeoJsonReferenceImporter())
    service = SourceWorkspaceService(
        database, router, id_factory=lambda: "geo-1", clock_us=lambda: 100
    )

    outcome = service.import_file(
        SubjectRef(SubjectType.PHOTO, "photo-1"),
        source_id="org.aperture.geojson-reference",
        input_path=source,
        parameters={"shape": "bounding_box", "source_version": "2026-Q3"},
    )

    assert outcome.created_enrichment_ids == ("geo-1",)
    record = CanonicalEnrichmentService(database).get("geo-1")
    assert record.enrichment_type == "bounding_box"
    assert record.payload["value"]["label"] == "Wetland"
    assert record.payload["target"]["bbox"] == {
        "min_x": 4.0,
        "min_y": 51.0,
        "max_x": 5.0,
        "max_y": 52.0,
    }
    assert record.source_snapshot["source_version"] == "2026-Q3"


def test_gtfs_importer_normalizes_stops(tmp_path: Path) -> None:
    database = _database(tmp_path)
    source = tmp_path / "transit.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon\nSTOP-1,Central Station,42.6977,23.3219\n",
        )
    router = InProcessSourceRouter()
    router.register(GtfsReferenceImporter())
    service = SourceWorkspaceService(
        database, router, id_factory=lambda: "gtfs-1", clock_us=lambda: 100
    )

    service.import_file(
        SubjectRef(SubjectType.OBSERVATION, "obs-1"),
        source_id="org.aperture.gtfs-reference",
        input_path=source,
        parameters={"licence": "Example licence"},
    )

    record = CanonicalEnrichmentService(database).get("gtfs-1")
    assert record.enrichment_type == "relationship"
    assert record.payload["value"] == {
        "relationship": "near_transit_stop",
        "target": "Central Station",
    }
    assert record.payload["external_id"] == "STOP-1"
    assert record.payload["target"]["latitude"] == 42.6977
    assert record.source_snapshot["licence"] == "Example licence"


def test_railml_importer_normalizes_operational_points(tmp_path: Path) -> None:
    database = _database(tmp_path)
    source = tmp_path / "network.railml"
    source.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
        <railml xmlns='https://www.railml.org/schemas/3.2'>
          <infrastructure>
            <operationalPoints>
              <operationalPoint id='op-1' name='North Junction' />
            </operationalPoints>
          </infrastructure>
        </railml>
        """,
        encoding="utf-8",
    )
    router = InProcessSourceRouter()
    router.register(RailMlReferenceImporter())
    service = SourceWorkspaceService(
        database, router, id_factory=lambda: "rail-1", clock_us=lambda: 100
    )

    service.import_file(
        SubjectRef(SubjectType.OBSERVATION, "obs-1"),
        source_id="org.aperture.railml-reference",
        input_path=source,
    )

    record = CanonicalEnrichmentService(database).get("rail-1")
    assert record.payload["value"] == {
        "relationship": "rail_operational_point",
        "target": "North Junction",
    }
    assert record.payload["external_id"] == "op-1"


def test_builtin_source_router_discovers_all_offline_importers() -> None:
    descriptors = create_builtin_source_router().discover()
    assert {item.source_id for item in descriptors} == {
        "org.aperture.csv-reference",
        "org.aperture.geojson-reference",
        "org.aperture.gtfs-reference",
        "org.aperture.railml-reference",
    }
    assert all(item.offline for item in descriptors)
