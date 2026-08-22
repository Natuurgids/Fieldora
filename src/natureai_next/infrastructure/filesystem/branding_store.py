"""TOML adapter for the application-owned branding persistence port."""

from __future__ import annotations

import tomllib
from pathlib import Path

from natureai_next.application.branding import BrandingSettings
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes
from natureai_next.infrastructure.filesystem.toml_codec import dumps_toml


class TomlBrandingStore:
    def load(self, path: Path) -> BrandingSettings:
        if not path.exists():
            return BrandingSettings()
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        values = document.get("branding", {})
        if not isinstance(values, dict):
            values = {}
        defaults = BrandingSettings()
        settings = BrandingSettings(
            **{
                field: str(values.get(field, getattr(defaults, field)))
                for field in defaults.__dataclass_fields__
            }
        )
        settings.validate()
        return settings

    def save(self, path: Path, settings: BrandingSettings) -> None:
        settings.validate()
        payload = {
            "branding": {
                "application_name": settings.application_name,
                "powered_by": settings.powered_by,
                "organization_name": settings.organization_name,
                "project_website": settings.project_website,
                "donation_label": settings.donation_label,
                "donation_url": settings.donation_url,
            }
        }
        atomic_write_bytes(path, dumps_toml(payload).encode("utf-8"))
