"""Offline enrichment execution layer.

This package deliberately has no dependency on Aperture persistence adapters.
"""

from natureai_next.synthesis_core.bioclip import BioCLIPCapability
from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityEngine,
    CapabilityRequest,
    CapabilityResult,
    ExtensionKind,
    InputKind,
    ParameterDefinition,
)
from natureai_next.synthesis_core.runtime import InProcessCapabilityRouter
from natureai_next.synthesis_core.sources import (
    CsvReferenceImporter,
    GeoJsonReferenceImporter,
    GtfsReferenceImporter,
    InProcessSourceRouter,
    RailMlReferenceImporter,
    SourceImporterDescriptor,
    SourceImportRequest,
    SourceImportResult,
    create_builtin_source_router,
)
from natureai_next.synthesis_core.test_sound import FixtureSoundEventCapability

__all__ = [
    "BioCLIPCapability",
    "CapabilityDescriptor",
    "CapabilityEngine",
    "CapabilityRequest",
    "CapabilityResult",
    "CsvReferenceImporter",
    "ExtensionKind",
    "FixtureSoundEventCapability",
    "GeoJsonReferenceImporter",
    "GtfsReferenceImporter",
    "InProcessCapabilityRouter",
    "InProcessSourceRouter",
    "InputKind",
    "ParameterDefinition",
    "RailMlReferenceImporter",
    "SourceImportRequest",
    "SourceImportResult",
    "SourceImporterDescriptor",
    "create_builtin_source_router",
]
