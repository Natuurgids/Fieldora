"""Configurable user-facing product identity for open-source distributions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class BrandingSettings:
    application_name: str = "Fieldora"
    powered_by: str = "NatureAI_Next"
    organization_name: str = "natuurgids.org"
    project_website: str = "https://natuurgids.org"
    donation_label: str = "Support Fieldora"
    donation_url: str = "https://natuurgids.org"

    def validate(self) -> None:
        if not self.application_name.strip():
            raise ValueError("Application name must not be blank")
        if not self.powered_by.strip():
            raise ValueError("Powered-by text must not be blank")
        for label, value in (
            ("Project website", self.project_website),
            ("Donation URL", self.donation_url),
        ):
            if value and urlparse(value).scheme.casefold() not in {"http", "https"}:
                raise ValueError(f"{label} must use http or https")


class BrandingStore(Protocol):
    """Persistence port for user-facing product identity."""

    def load(self, path: Path) -> BrandingSettings: ...

    def save(self, path: Path, settings: BrandingSettings) -> None: ...
