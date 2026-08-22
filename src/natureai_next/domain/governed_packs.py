"""Canonical manifests for policy-filtered Phase E project data packs."""

from __future__ import annotations

from dataclasses import dataclass

GOVERNED_PACK_FORMAT = "fieldora.governed-project-pack"
GOVERNED_PACK_VERSION = 1


@dataclass(frozen=True, slots=True)
class GovernedPackSummary:
    pack_id: str
    enrollment_id: str
    project_id: str
    version: int
    base_version: int
    record_count: int
    tombstone_count: int
    package_sha256: str

