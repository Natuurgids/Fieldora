"""Stable lifecycle states for optional Aperture subsystems."""

from __future__ import annotations

from enum import StrEnum


class SubsystemState(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    UNHEALTHY = "unhealthy"
