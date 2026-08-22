"""Validation and loading for Aperture-owned offline vector styles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_SOURCE_LAYERS = frozenset({"landuse", "water", "building", "transportation", "place"})


def load_aperture_street_style(path: Path, tile_url: str) -> dict[str, Any]:
    style = json.loads(path.read_text(encoding="utf-8"))
    if (
        style.get("version") != 8
        or style.get("metadata", {}).get("aperture:schema") != "aperture-streets-v2"
    ):
        raise ValueError("unsupported Aperture vector style schema")
    if style.get("glyphs") or style.get("sprite"):
        raise ValueError("unapproved glyph or sprite resource in offline style")
    if style.get("metadata", {}).get("aperture:labels") != "offline-dom-labels":
        raise ValueError("offline style must use the approved local-font label policy")
    sources = style.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"aperture"}:
        raise ValueError("offline style must contain exactly the Aperture source")
    source = sources["aperture"]
    if source.get("type") != "vector" or source.get("url") != "__APERTURE_PMTILES_URL__":
        raise ValueError("offline style source is invalid")
    layers = style.get("layers")
    if not isinstance(layers, list):
        raise ValueError("offline style layers are missing")
    observed = {
        layer.get("source-layer")
        for layer in layers
        if isinstance(layer, dict) and layer.get("source") == "aperture"
    }
    if observed != REQUIRED_SOURCE_LAYERS:
        raise ValueError("offline style does not match the Aperture street schema")
    rendered = json.loads(json.dumps(style))
    rendered["sources"]["aperture"].pop("url", None)
    rendered["sources"]["aperture"]["tiles"] = [tile_url]
    return rendered
