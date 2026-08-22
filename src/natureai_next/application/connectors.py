"""Offline connector registry and preflight validation.

No network calls are made here. Service-specific upload adapters can implement the
same contracts later without coupling credentials to the library database.
"""
from __future__ import annotations
from natureai_next.domain.connectors import ConnectorCapability, ConnectorDefinition, ConnectorValidation
from natureai_next.domain.exporting import ExportAssetRecord

_BUILT_INS = (
    ConnectorDefinition("waarneming-nl", "Waarneming.nl", "https://waarneming.nl", (ConnectorCapability.OBSERVATION_UPLOAD, ConnectorCapability.MEDIA_UPLOAD, ConnectorCapability.TAXON_LOOKUP), ("scientific_name", "capture_time", "location"), {"scientific_name":"species","capture_time":"date","latitude":"lat","longitude":"lng","count":"number"}),
    ConnectorDefinition("observation-org", "Observation.org", "https://observation.org", (ConnectorCapability.OBSERVATION_UPLOAD, ConnectorCapability.MEDIA_UPLOAD, ConnectorCapability.TAXON_LOOKUP), ("scientific_name", "capture_time", "location"), {"scientific_name":"species","capture_time":"date","latitude":"lat","longitude":"lng","count":"number"}),
    ConnectorDefinition("inaturalist", "iNaturalist", "https://www.inaturalist.org", (ConnectorCapability.OBSERVATION_UPLOAD, ConnectorCapability.MEDIA_UPLOAD, ConnectorCapability.TAXON_LOOKUP), ("scientific_name", "capture_time"), {"scientific_name":"taxon_name","capture_time":"observed_on_string","count":"quantity"}),
    ConnectorDefinition("gbif", "GBIF", "https://www.gbif.org", (ConnectorCapability.TAXON_LOOKUP,), ("scientific_name",), {"scientific_name":"scientificName"}, authentication="none"),
)

class ConnectorRegistry:
    def __init__(self, definitions: tuple[ConnectorDefinition, ...] = _BUILT_INS) -> None:
        self._definitions = {item.connector_id: item for item in definitions}
    def list(self) -> tuple[ConnectorDefinition, ...]:
        return tuple(self._definitions.values())
    def get(self, connector_id: str) -> ConnectorDefinition:
        return self._definitions[connector_id]
    def validate(self, connector_id: str, records: tuple[ExportAssetRecord, ...]) -> ConnectorValidation:
        definition = self.get(connector_id)
        valid=invalid=0; warnings=[]; errors=[]
        for asset in records:
            if not asset.observations:
                invalid += 1; continue
            for observation in asset.observations:
                missing=[]
                if "scientific_name" in definition.required_fields and not observation.get("scientific_name"):
                    missing.append("scientific name")
                if "capture_time" in definition.required_fields and not (asset.capture_time_utc_us or asset.capture_local_text):
                    missing.append("capture time")
                if "location" in definition.required_fields:
                    # Existing export projection does not yet expose location; preflight remains explicit.
                    missing.append("location")
                if missing:
                    invalid += 1
                    warnings.append(f"{asset.public_id}: missing {', '.join(missing)}")
                else:
                    valid += 1
        if not records:
            errors.append("No records selected")
        return ConnectorValidation(connector_id, valid, invalid, tuple(warnings[:100]), tuple(errors))
