"""Portable Fieldora project package contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


SCIENCE_PACKAGE_FORMAT = "fieldora.portable-project"
SCIENCE_PACKAGE_VERSION = 1


class ProjectCollisionPolicy(StrEnum):
    FAIL = "fail"
    SKIP = "skip"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class ProjectPackageSummary:
    project_id: str
    project_name: str
    record_count: int
    library_reference_count: int
    includes_originals: bool
    package_sha256: str = ""


@dataclass(frozen=True, slots=True)
class ProjectImportPlan:
    summary: ProjectPackageSummary
    collisions: tuple[tuple[str, str], ...]
    policy: ProjectCollisionPolicy

    @property
    def can_apply(self) -> bool:
        return self.policy is not ProjectCollisionPolicy.FAIL or not self.collisions
