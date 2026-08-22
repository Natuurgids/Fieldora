"""Catalog-backed discovery for optional AI models."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

ENTRY_POINT_GROUP = "aperture.models"


@dataclass(frozen=True, slots=True)
class DependencySpec:
    import_name: str
    pip_requirement: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    key: str
    display_name: str
    factory: str
    family: str = "generic"
    version: str | None = None
    requirements: tuple[DependencySpec, ...] = ()
    factory_kwargs: dict[str, Any] = field(default_factory=dict)
    input_contract: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    ui_contract: dict[str, Any] = field(default_factory=dict)
    default: bool = False
    built_in: bool = False
    description: str = ""
    license_name: str = ""
    license_url: str | None = None
    requires_license_acceptance: bool = False
    estimated_download_mb: int | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ModelSpec:
        requirements = tuple(
            DependencySpec(str(item["import"]), str(item.get("pip") or item["import"]))
            for item in value.get("requirements", ())
        )
        return cls(
            key=str(value["key"]),
            display_name=str(value.get("display_name") or value["key"]),
            factory=str(value["factory"]),
            family=str(value.get("family") or "generic"),
            version=None if value.get("version") is None else str(value["version"]),
            requirements=requirements,
            factory_kwargs=dict(value.get("factory_kwargs") or {}),
            input_contract=dict(value.get("input") or {}),
            output_contract=dict(value.get("output") or {}),
            ui_contract=dict(value.get("ui") or {}),
            default=bool(value.get("default", False)),
            built_in=bool(value.get("built_in", False)),
            description=str(value.get("description") or ""),
            license_name=str(value.get("license") or ""),
            license_url=(None if value.get("license_url") is None else str(value["license_url"])),
            requires_license_acceptance=bool(value.get("requires_license_acceptance", False)),
            estimated_download_mb=(
                None
                if value.get("estimated_download_mb") is None
                else int(value["estimated_download_mb"])
            ),
        )


class ModelCatalog:
    def __init__(self, specs: Iterable[ModelSpec]) -> None:
        self._specs = {item.key: item for item in specs}
        if len(self._specs) != len(tuple(self._specs.values())):
            raise ValueError("duplicate model key")

    @classmethod
    def load(cls, path: Path, *, include_entry_points: bool = True) -> ModelCatalog:
        raw = json.loads(path.read_text(encoding="utf-8"))
        specs = [ModelSpec.from_mapping(item) for item in raw.get("models", ())]
        if include_entry_points:
            specs.extend(discover_entry_point_models())
        merged: dict[str, ModelSpec] = {}
        for spec in specs:
            merged[spec.key] = spec
        return cls(merged.values())

    def list(self) -> tuple[ModelSpec, ...]:
        return tuple(
            sorted(
                self._specs.values(),
                key=lambda item: (not item.default, item.display_name.casefold()),
            )
        )

    def get(self, key: str) -> ModelSpec:
        try:
            return self._specs[key]
        except KeyError as exc:
            raise KeyError(f"unknown model key: {key}") from exc

    @property
    def default_key(self) -> str:
        for spec in self.list():
            if spec.default:
                return spec.key
        if not self._specs:
            raise RuntimeError("model catalog is empty")
        return self.list()[0].key


def discover_entry_point_models() -> tuple[ModelSpec, ...]:
    found: list[ModelSpec] = []
    points = metadata.entry_points()
    selected = (
        points.select(group=ENTRY_POINT_GROUP)
        if hasattr(points, "select")
        else points.get(ENTRY_POINT_GROUP, ())
    )
    for point in selected:
        payload = point.load()
        if callable(payload):
            payload = payload()
        values = payload if isinstance(payload, list | tuple) else (payload,)
        for value in values:
            if isinstance(value, ModelSpec):
                found.append(value)
            elif isinstance(value, dict):
                found.append(ModelSpec.from_mapping(value))
            else:
                raise TypeError(f"entry point {point.name!r} returned unsupported model metadata")
    return tuple(found)
