"""Connector contracts and validation models."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

class ConnectorCapability(StrEnum):
    OBSERVATION_UPLOAD = "observation_upload"
    MEDIA_UPLOAD = "media_upload"
    TAXON_LOOKUP = "taxon_lookup"
    STATUS_SYNC = "status_sync"

@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    connector_id: str
    display_name: str
    service_url: str
    capabilities: tuple[ConnectorCapability, ...]
    required_fields: tuple[str, ...]
    field_mapping: Mapping[str, str]
    authentication: str = "oauth2"

@dataclass(frozen=True, slots=True)
class ConnectorValidation:
    connector_id: str
    valid_count: int
    invalid_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
