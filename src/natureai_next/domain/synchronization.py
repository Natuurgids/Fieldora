"""Phase E desktop synchronization identities, enrollments, and effective rights."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit


class EnrollmentState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SyncItemState(StrEnum):
    PENDING = "pending"
    INFLIGHT = "inflight"
    APPLIED = "applied"
    RETRY = "retry"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PlatformAccount:
    account_id: str
    endpoint_url: str
    display_name: str
    organization_id: str
    subject_id: str
    created_at_utc: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("platform endpoint must be an HTTPS origin without credentials")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("platform endpoint must not include a path, query, or fragment")
        if not all((self.account_id, self.display_name.strip(), self.organization_id, self.subject_id)):
            raise ValueError("account identity fields are required")


@dataclass(frozen=True, slots=True)
class RegisteredDesktopDevice:
    device_id: str
    account_id: str
    server_device_id: str
    display_name: str
    registered_at_utc: str
    revoked_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class ProjectEnrollment:
    enrollment_id: str
    account_id: str
    project_id: str
    contract_id: str
    state: EnrollmentState
    rights: tuple[str, ...]
    expires_at_utc: str
    revision: int
    acknowledged_at_utc: str

    def effective_rights(self, at_utc: str) -> tuple[str, ...]:
        if (
            self.state is not EnrollmentState.ACTIVE
            or not self.acknowledged_at_utc
            or (self.expires_at_utc and at_utc >= self.expires_at_utc)
        ):
            return ()
        return tuple(sorted(set(self.rights)))


@dataclass(frozen=True, slots=True)
class SyncChange:
    change_id: str
    enrollment_id: str
    idempotency_key: str
    aggregate_type: str
    aggregate_id: str
    base_revision: int
    payload: dict[str, Any]
    tombstone: bool
    state: SyncItemState = SyncItemState.PENDING
    attempt_count: int = 0
    next_attempt_at_utc: str = ""
    lease_until_utc: str = ""


@dataclass(frozen=True, slots=True)
class SyncConflict:
    conflict_id: str
    enrollment_id: str
    aggregate_type: str
    aggregate_id: str
    local_revision: int
    remote_revision: int
    local_payload: dict[str, Any]
    remote_payload: dict[str, Any]
    created_at_utc: str
    resolved_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class MediaTransfer:
    transfer_id: str
    enrollment_id: str
    media_id: str
    destination_path: str
    expected_size: int
    expected_sha256: str
    etag: str
    offset: int = 0
    state: str = "pending"


@dataclass(frozen=True, slots=True)
class ContributionAcknowledgment:
    acknowledgment_id: str
    enrollment_id: str
    enrollment_revision: int
    license_id: str
    terms_sha256: str
    acknowledged_by: str
    acknowledged_at_utc: str
