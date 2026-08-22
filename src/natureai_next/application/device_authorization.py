"""Short-lived, one-time device authorization flow."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from natureai_next.application.access_control import AccessAdministrationService
from natureai_next.application.authentication import AuthenticationService
from natureai_next.domain.access_control import IdentityKind
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


@dataclass(frozen=True, slots=True)
class DeviceCode:
    device_code: str
    user_code: str
    expires_at_utc: str


class DeviceAuthorizationPending(RuntimeError):
    pass


class DeviceAuthorizationService:
    def __init__(
        self, repository: SqliteAccessControlRepository,
        authentication: AuthenticationService,
    ) -> None:
        self._repository = repository
        self._authentication = authentication

    def begin(self, device_name: str, organization_id: str, project_id: str) -> DeviceCode:
        now = datetime.now(UTC)
        device_code = secrets.token_urlsafe(48)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw_user = "".join(secrets.choice(alphabet) for _ in range(8))
        user_code = f"{raw_user[:4]}-{raw_user[4:]}"
        expires = now + timedelta(minutes=10)
        self._repository.put_device_authorization(
            {
                "authorization_id": str(uuid4()),
                "device_code_hash": self._hash(device_code),
                "user_code_hash": self._hash(user_code),
                "device_name": device_name.strip()[:100],
                "organization_id": organization_id.strip(),
                "project_id": project_id.strip(),
                "created_at_utc": now.isoformat(),
                "expires_at_utc": expires.isoformat(),
            }
        )
        return DeviceCode(device_code, user_code, expires.isoformat())

    def approve(self, user_code: str, approver_id: str) -> str:
        record = self.pending(user_code)
        now = datetime.now(UTC).isoformat()
        if (
            record is None or record["expires_at_utc"] <= now
            or record["approved_at_utc"] or record["consumed_at_utc"]
        ):
            raise ValueError("device code is invalid or expired")
        administration = AccessAdministrationService(self._repository)
        device = administration.create_identity(
            str(record["device_name"]), str(record["organization_id"]),
            IdentityKind.DEVICE,
        )
        administration.grant_role(
            device.identity_id, "field-device", str(record["organization_id"]),
            str(record["project_id"]),
        )
        if not self._repository.approve_device_authorization(
            str(record["authorization_id"]), approver_id, device.identity_id, now
        ):
            raise ValueError("device code was already approved")
        return device.identity_id

    def pending(self, user_code: str) -> dict | None:
        return self._repository.device_authorization(
            "user_code_hash", self._hash(user_code.strip().upper())
        )

    def exchange(self, device_code: str) -> tuple[str, str]:
        record = self._repository.device_authorization(
            "device_code_hash", self._hash(device_code)
        )
        now = datetime.now(UTC).isoformat()
        if record is None or record["expires_at_utc"] <= now or record["consumed_at_utc"]:
            raise ValueError("device code is invalid, expired, or consumed")
        if not record["approved_identity_id"]:
            raise DeviceAuthorizationPending("authorization pending")
        if not self._repository.consume_device_authorization(
            str(record["authorization_id"]), now
        ):
            raise ValueError("device code was already consumed")
        return self._authentication.issue_machine_key(
            str(record["approved_identity_id"]),
            f"device-flow:{record['project_id']}",
            timedelta(days=30),
        )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
