"""Stable source/importer execution contracts for offline enrichment providers."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from natureai_next.domain.enrichment import CanonicalCandidate, CanonicalShape


@dataclass(frozen=True, slots=True)
class SourceImportRequest:
    source_id: str
    subject_public_id: str
    input_path: Path
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceImportResult:
    source_id: str
    producer_name: str
    producer_version: str
    candidates: tuple[CanonicalCandidate, ...]
    source_name: str
    source_version: str
    source_checksum: str | None = None
    attribution: str | None = None
    licence: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceImporterDescriptor:
    source_id: str
    display_name: str
    version: str
    supported_suffixes: frozenset[str]
    output_shapes: frozenset[str]
    offline: bool = True


@runtime_checkable
class SourceImporter(Protocol):
    descriptor: SourceImporterDescriptor

    def import_candidates(self, request: SourceImportRequest) -> SourceImportResult: ...

    def release(self) -> None: ...


class InProcessSourceRouter:
    """Small one-process router mirroring the capability router boundary."""

    def __init__(self) -> None:
        self._importers: dict[str, SourceImporter] = {}
        self._active: set[str] = set()

    def register(self, importer: SourceImporter, *, active: bool = True) -> None:
        source_id = importer.descriptor.source_id
        if source_id in self._importers:
            raise ValueError(f"source importer already registered: {source_id}")
        self._importers[source_id] = importer
        if active:
            self._active.add(source_id)

    def discover(self) -> Sequence[SourceImporterDescriptor]:
        return tuple(item.descriptor for item in self._importers.values())

    def activate(self, source_id: str) -> None:
        if source_id not in self._importers:
            raise KeyError(f"unknown source importer: {source_id}")
        self._active.add(source_id)

    def deactivate(self, source_id: str) -> None:
        self._active.discard(source_id)
        importer = self._importers.get(source_id)
        if importer is not None:
            importer.release()

    def execute(self, request: SourceImportRequest) -> SourceImportResult:
        importer = self._importers.get(request.source_id)
        if importer is None:
            raise KeyError(f"unknown source importer: {request.source_id}")
        if request.source_id not in self._active:
            raise RuntimeError(f"source importer is inactive: {request.source_id}")
        suffix = request.input_path.suffix.casefold()
        if suffix not in importer.descriptor.supported_suffixes:
            raise ValueError(f"unsupported source file type: {suffix or '<none>'}")
        return importer.import_candidates(request)


class CsvReferenceImporter:
    """Offline CSV importer producing label, relationship or measurement candidates.

    Rows are intentionally producer-neutral.  The caller chooses the output shape and
    column mapping through parameters, allowing small reference datasets to exercise
    the same source lifecycle used by future GBIF, GTFS and GeoPackage importers.
    """

    descriptor = SourceImporterDescriptor(
        source_id="org.aperture.csv-reference",
        display_name="CSV Reference Importer",
        version="1.0.0",
        supported_suffixes=frozenset({".csv"}),
        output_shapes=frozenset(
            {
                CanonicalShape.LABEL.value,
                CanonicalShape.RELATIONSHIP.value,
                CanonicalShape.MEASUREMENT.value,
            }
        ),
    )

    def import_candidates(self, request: SourceImportRequest) -> SourceImportResult:
        shape = CanonicalShape(str(request.parameters.get("shape", CanonicalShape.LABEL.value)))
        if shape.value not in self.descriptor.output_shapes:
            raise ValueError(f"CSV importer does not support shape: {shape.value}")
        value_column = str(request.parameters.get("value_column", "value"))
        external_id_column = request.parameters.get("external_id_column")
        confidence_column = request.parameters.get("confidence_column")
        candidates: list[CanonicalCandidate] = []
        with request.input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or value_column not in reader.fieldnames:
                raise ValueError(f"CSV is missing required column: {value_column}")
            for row_number, row in enumerate(reader, start=2):
                raw = (row.get(value_column) or "").strip()
                if not raw:
                    continue
                confidence = None
                if confidence_column:
                    confidence_text = (row.get(str(confidence_column)) or "").strip()
                    if confidence_text:
                        confidence = float(confidence_text)
                external_id = None
                if external_id_column:
                    external_id = (row.get(str(external_id_column)) or "").strip() or None
                value: dict[str, Any]
                if shape is CanonicalShape.MEASUREMENT:
                    value = {
                        "name": str(request.parameters.get("measurement_name", value_column)),
                        "value": float(raw),
                    }
                    unit = request.parameters.get("unit")
                    if unit:
                        value["unit"] = str(unit)
                elif shape is CanonicalShape.RELATIONSHIP:
                    value = {
                        "relationship": str(request.parameters.get("relationship", "references")),
                        "target": raw,
                    }
                else:
                    value = {"label": raw}
                candidates.append(
                    CanonicalCandidate(
                        shape=shape,
                        value=value,
                        confidence=confidence,
                        external_id=external_id,
                        target={"source_row": row_number},
                    )
                )
        return SourceImportResult(
            source_id=self.descriptor.source_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name=request.input_path.name,
            source_version=str(request.parameters.get("source_version", "local")),
            attribution=request.parameters.get("attribution"),
            licence=request.parameters.get("licence"),
            diagnostics={"rows_imported": len(candidates)},
        )

    def release(self) -> None:
        return None


class GeoJsonReferenceImporter:
    """Offline GeoJSON importer producing spatial or relationship candidates."""

    descriptor = SourceImporterDescriptor(
        source_id="org.aperture.geojson-reference",
        display_name="GeoJSON Reference Importer",
        version="1.0.0",
        supported_suffixes=frozenset({".geojson", ".json"}),
        output_shapes=frozenset(
            {CanonicalShape.BOUNDING_BOX.value, CanonicalShape.RELATIONSHIP.value}
        ),
    )

    def import_candidates(self, request: SourceImportRequest) -> SourceImportResult:
        import json

        document = json.loads(request.input_path.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            raise ValueError("GeoJSON root must be an object")
        root_type = str(document.get("type", ""))
        if root_type == "FeatureCollection":
            features = document.get("features", [])
        elif root_type == "Feature":
            features = [document]
        else:
            raise ValueError("GeoJSON must be a Feature or FeatureCollection")
        if not isinstance(features, list):
            raise ValueError("GeoJSON features must be an array")

        shape = CanonicalShape(
            str(request.parameters.get("shape", CanonicalShape.RELATIONSHIP.value))
        )
        if shape.value not in self.descriptor.output_shapes:
            raise ValueError(f"GeoJSON importer does not support shape: {shape.value}")
        label_property = str(request.parameters.get("label_property", "name"))
        relationship = str(request.parameters.get("relationship", "spatially_references"))
        candidates: list[CanonicalCandidate] = []
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties") or {}
            if not isinstance(properties, dict):
                properties = {}
            geometry = feature.get("geometry")
            bounds = _geojson_bounds(geometry)
            if bounds is None:
                continue
            label = str(
                properties.get(label_property) or feature.get("id") or f"feature-{index + 1}"
            )
            target = {
                "geometry": geometry,
                "bbox": {
                    "min_x": bounds[0],
                    "min_y": bounds[1],
                    "max_x": bounds[2],
                    "max_y": bounds[3],
                },
                "feature_index": index,
            }
            if shape is CanonicalShape.BOUNDING_BOX:
                value = {"label": label, **target["bbox"]}
            else:
                value = {"relationship": relationship, "target": label}
            candidates.append(
                CanonicalCandidate(
                    shape=shape,
                    value=value,
                    external_id=None if feature.get("id") is None else str(feature["id"]),
                    target=target,
                )
            )
        return SourceImportResult(
            source_id=self.descriptor.source_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name=request.input_path.name,
            source_version=str(request.parameters.get("source_version", "local")),
            attribution=request.parameters.get("attribution"),
            licence=request.parameters.get("licence"),
            diagnostics={"features_imported": len(candidates)},
        )

    def release(self) -> None:
        return None


class GtfsReferenceImporter:
    """Offline GTFS package importer producing stop relationship candidates."""

    descriptor = SourceImporterDescriptor(
        source_id="org.aperture.gtfs-reference",
        display_name="GTFS Reference Importer",
        version="1.0.0",
        supported_suffixes=frozenset({".zip"}),
        output_shapes=frozenset({CanonicalShape.RELATIONSHIP.value}),
    )

    def import_candidates(self, request: SourceImportRequest) -> SourceImportResult:
        import io
        import zipfile

        candidates: list[CanonicalCandidate] = []
        relationship = str(request.parameters.get("relationship", "near_transit_stop"))
        with zipfile.ZipFile(request.input_path) as archive:
            names = {name.casefold(): name for name in archive.namelist()}
            stop_member = names.get("stops.txt")
            if stop_member is None:
                raise ValueError("GTFS package is missing stops.txt")
            with archive.open(stop_member) as binary:
                reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
                required = {"stop_id", "stop_name"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise ValueError("GTFS stops.txt must contain stop_id and stop_name")
                for row_number, row in enumerate(reader, start=2):
                    stop_id = (row.get("stop_id") or "").strip()
                    stop_name = (row.get("stop_name") or "").strip()
                    if not stop_id or not stop_name:
                        continue
                    target: dict[str, Any] = {"source_row": row_number}
                    latitude = (row.get("stop_lat") or "").strip()
                    longitude = (row.get("stop_lon") or "").strip()
                    if latitude and longitude:
                        target["latitude"] = float(latitude)
                        target["longitude"] = float(longitude)
                    candidates.append(
                        CanonicalCandidate(
                            shape=CanonicalShape.RELATIONSHIP,
                            value={"relationship": relationship, "target": stop_name},
                            external_id=stop_id,
                            target=target,
                        )
                    )
        return SourceImportResult(
            source_id=self.descriptor.source_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name=request.input_path.name,
            source_version=str(request.parameters.get("source_version", "local")),
            attribution=request.parameters.get("attribution"),
            licence=request.parameters.get("licence"),
            diagnostics={"stops_imported": len(candidates)},
        )

    def release(self) -> None:
        return None


class RailMlReferenceImporter:
    """Offline railML importer producing operational-point relationships."""

    descriptor = SourceImporterDescriptor(
        source_id="org.aperture.railml-reference",
        display_name="railML Reference Importer",
        version="1.0.0",
        supported_suffixes=frozenset({".railml", ".xml"}),
        output_shapes=frozenset({CanonicalShape.RELATIONSHIP.value}),
    )

    def import_candidates(self, request: SourceImportRequest) -> SourceImportResult:
        import xml.etree.ElementTree as ET

        relationship = str(request.parameters.get("relationship", "rail_operational_point"))
        candidates: list[CanonicalCandidate] = []
        for _event, element in ET.iterparse(request.input_path, events=("end",)):
            local_name = element.tag.rsplit("}", 1)[-1].casefold()
            if local_name not in {"operationalpoint", "ocp"}:
                continue
            external_id = element.get("id") or element.get("code")
            name = element.get("name") or element.get("code") or external_id
            if not name:
                name_node = next(
                    (
                        child
                        for child in element
                        if child.tag.rsplit("}", 1)[-1].casefold() in {"name", "designator"}
                    ),
                    None,
                )
                if name_node is not None and name_node.text:
                    name = name_node.text.strip()
            if name:
                candidates.append(
                    CanonicalCandidate(
                        shape=CanonicalShape.RELATIONSHIP,
                        value={"relationship": relationship, "target": str(name)},
                        external_id=None if external_id is None else str(external_id),
                    )
                )
            element.clear()
        return SourceImportResult(
            source_id=self.descriptor.source_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=tuple(candidates),
            source_name=request.input_path.name,
            source_version=str(request.parameters.get("source_version", "local")),
            attribution=request.parameters.get("attribution"),
            licence=request.parameters.get("licence"),
            diagnostics={"operational_points_imported": len(candidates)},
        )

    def release(self) -> None:
        return None


def _geojson_bounds(geometry: object) -> tuple[float, float, float, float] | None:
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    points: list[tuple[float, float]] = []

    def collect(value: object) -> None:
        if isinstance(value, list | tuple):
            if len(value) >= 2 and all(isinstance(item, int | float) for item in value[:2]):
                points.append((float(value[0]), float(value[1])))
            else:
                for item in value:
                    collect(item)

    collect(coordinates)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def create_builtin_source_router() -> InProcessSourceRouter:
    """Return the locally available producer-neutral source importers.

    This factory keeps desktop composition independent from concrete importer names
    while ensuring that every bundled importer participates in the same activation
    and cleanup lifecycle.
    """
    router = InProcessSourceRouter()
    for importer in (
        CsvReferenceImporter(),
        GeoJsonReferenceImporter(),
        GtfsReferenceImporter(),
        RailMlReferenceImporter(),
    ):
        router.register(importer)
    return router
