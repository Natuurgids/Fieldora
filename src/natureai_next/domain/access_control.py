"""Identity, contract, and policy-based access-control domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class IdentityKind(StrEnum):
    USER = "user"
    GROUP = "group"
    SERVICE = "service"
    DEVICE = "device"


class PolicyEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class PolicySource(StrEnum):
    DIRECT = "direct"
    ROLE = "role"
    CONTRACT = "contract"
    OBJECT_GRANT = "object_grant"


@dataclass(frozen=True, slots=True)
class Organization:
    organization_id: str
    name: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class Identity:
    identity_id: str
    kind: IdentityKind
    display_name: str
    organization_id: str
    enabled: bool = True
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Contract:
    contract_id: str
    title: str
    organization_id: str
    starts_at_utc: str
    ends_at_utc: str
    status: str
    terms: dict[str, object] = field(default_factory=dict)

    def active_at(self, at_utc: str) -> bool:
        return (
            self.status == "active"
            and (not self.starts_at_utc or self.starts_at_utc <= at_utc)
            and (not self.ends_at_utc or at_utc < self.ends_at_utc)
        )


@dataclass(frozen=True, slots=True)
class Policy:
    policy_id: str
    name: str
    effect: PolicyEffect
    source: PolicySource
    source_id: str
    subject_id: str
    role_id: str
    actions: tuple[str, ...]
    resource_types: tuple[str, ...]
    resource_id: str = ""
    organization_id: str = ""
    project_id: str = ""
    purposes: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    conditions: dict[str, str] = field(default_factory=dict)
    valid_from_utc: str = ""
    valid_until_utc: str = ""
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AccessRequest:
    subject_id: str
    action: str
    resource_type: str
    resource_id: str = ""
    organization_id: str = ""
    project_id: str = ""
    purpose: str = ""
    fields: tuple[str, ...] = ()
    attributes: dict[str, str] = field(default_factory=dict)
    requested_at_utc: str = ""

    def effective_time(self) -> str:
        return self.requested_at_utc or datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    reason: str
    matched_policy_ids: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] = ()
