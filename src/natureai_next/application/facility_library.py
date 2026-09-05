"""Bridge versioned facility drawings to governed Fieldora Library assets.

Operations owns the spatial/version relationship; the Library owns preserved
files, checksums, metadata and searchability.  No duplicate document store is
introduced for facilities.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from natureai_next.application.asset_catalog import AssetCatalogService
from natureai_next.application.operations_assets import OperationsAssetService


class FacilityDrawingLibraryBridge:
    """Resolve and link Library assets used by facility drawing revisions."""

    def __init__(
        self,
        operations: OperationsAssetService,
        library_database: str | Path,
    ) -> None:
        self.operations = operations
        self.library_database = Path(library_database)
        self.catalog = AssetCatalogService(self.library_database)

    def searchable_drawing_assets(self, search: str = "", limit: int = 500):
        """Return likely drawing/reference assets already present in the Library."""
        candidates = self.catalog.list_assets(asset_type="all", search=search, limit=limit)
        allowed = {"document", "map", "photo", "other"}
        drawing_extensions = {
            ".svg",
            ".pdf",
            ".dwg",
            ".dxf",
            ".ifc",
            ".ifczip",
            ".vsdx",
            ".vdx",
            ".eddx",
            ".edxz",
            ".tif",
            ".tiff",
            ".png",
            ".jpg",
            ".jpeg",
        }
        return tuple(
            asset
            for asset in candidates
            if asset.asset_type in allowed
            and (
                Path(asset.path).suffix.casefold() in drawing_extensions
                or any(
                    term in asset.title.casefold()
                    for term in ("drawing", "floorplan", "floor plan", "blueprint", "layout", "architect", "cad", "bim")
                )
            )
        )

    def library_asset(self, asset_public_id: str) -> dict[str, Any]:
        """Resolve one active Library asset and its primary file metadata."""
        with sqlite3.connect(self.library_database) as cx:
            cx.row_factory = sqlite3.Row
            row = cx.execute(
                """SELECT a.public_id,a.title,a.caption,a.user_notes,a.lifecycle_state,
                          f.normalized_path,f.mime_type,f.file_size,f.sha256
                     FROM assets a
                     LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                    WHERE a.public_id=?""",
                (asset_public_id,),
            ).fetchone()
        if row is None or str(row["lifecycle_state"]) != "active":
            raise KeyError(asset_public_id)
        return dict(row)

    def link_source_asset(
        self,
        drawing_id: str,
        library_asset_id: str,
        *,
        actor: str,
        relationship: str = "reference",
        notes: str = "",
    ) -> str:
        asset = self.library_asset(library_asset_id)
        path = str(asset.get("normalized_path") or "")
        return self.operations.link_drawing_source(
            drawing_id,
            actor=actor,
            library_asset_id=library_asset_id,
            relationship=relationship,
            title=str(asset.get("title") or Path(path).name or library_asset_id),
            source_format=Path(path).suffix.casefold().lstrip("."),
            file_path=path,
            notes=notes,
        )

    def set_operational_svg_asset(
        self,
        drawing_id: str,
        library_asset_id: str,
        *,
        actor: str,
    ) -> None:
        asset = self.library_asset(library_asset_id)
        path = str(asset.get("normalized_path") or "")
        if Path(path).suffix.casefold() != ".svg":
            raise ValueError("The operational floorplan Library asset must be an SVG")
        self.operations.set_operational_svg(
            drawing_id,
            actor=actor,
            svg_path=path,
            library_asset_id=library_asset_id,
        )

    def drawing_library_context(self, drawing_id: str, actor: str = "local-user") -> dict[str, Any]:
        drawing = self.operations.drawing(drawing_id, actor)
        sources = []
        for source in self.operations.drawing_sources(drawing_id, actor):
            item = dict(source)
            library_id = str(item.get("library_asset_id") or "")
            if library_id:
                try:
                    item["library"] = self.library_asset(library_id)
                except KeyError:
                    item["library"] = None
            sources.append(item)
        operational = None
        operational_id = str(drawing.get("operational_svg_asset_id") or "")
        if operational_id:
            try:
                operational = self.library_asset(operational_id)
            except KeyError:
                operational = None
        return {
            "drawing": drawing,
            "operational_svg": operational,
            "sources": tuple(sources),
        }
