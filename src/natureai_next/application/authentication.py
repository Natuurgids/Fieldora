"""Local credential and opaque-session authentication for the reference server."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


class AuthenticationFailed(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    token: str
    identity: Identity
    expires_at_utc: str


class AuthenticationService:
    ITERATIONS = 310_000

    def __init__(
        self, repository: SqliteAccessControlRepository,
        session_lifetime: timedelta = timedelta(hours=8),
    ) -> None:
        self._repository = repository
        self._session_lifetime = session_lifetime

    def set_password(self, identity_id: str, username: str, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        identity = self._repository.identity(identity_id)
        if identity is None or not identity.enabled:
            raise ValueError("Identity is unknown or disabled")
        normalized = username.strip().casefold()
        if not normalized:
            raise ValueError("Username is required")
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, self.ITERATIONS
        )
        self._repository.put_credential(
            identity_id, normalized, salt.hex(), digest.hex(), self.ITERATIONS
        )

    def login(
        self, username: str, password: str, client_label: str = "web"
    ) -> AuthenticatedSession:
        credential = self._repository.credential(username.strip().casefold())
        if credential is None or not bool(credential["enabled"]):
            self._dummy_verify(password)
            raise AuthenticationFailed("Invalid username or password")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(credential["salt_hex"]),
            int(credential["iterations"]),
        )
        if not hmac.compare_digest(digest.hex(), str(credential["password_hash_hex"])):
            raise AuthenticationFailed("Invalid username or password")
        identity = self._repository.identity(str(credential["identity_id"]))
        if identity is None or not identity.enabled:
            raise AuthenticationFailed("Identity is disabled")
        now = datetime.now(UTC)
        expires = now + self._session_lifetime
        token = secrets.token_urlsafe(48)
        self._repository.put_session(
            token, identity.identity_id, now.isoformat(), expires.isoformat(),
            client_label[:100],
        )
        return AuthenticatedSession(token, identity, expires.isoformat())

    def authenticate(self, token: str) -> Identity:
        now = datetime.now(UTC).isoformat()
        record = self._repository.session(token, now)
        if record is None:
            raise AuthenticationFailed("Session is invalid or expired")
        identity = self._repository.identity(str(record["identity_id"]))
        if identity is None or not identity.enabled:
            raise AuthenticationFailed("Identity is disabled")
        return identity

    def logout(self, token: str) -> None:
        self._repository.revoke_session(token, datetime.now(UTC).isoformat())

    def issue_service_key(
        self, identity_id: str, label: str, lifetime: timedelta = timedelta(days=90)
    ) -> tuple[str, str]:
        return self.issue_machine_key(identity_id, label, lifetime)

    def issue_machine_key(
        self, identity_id: str, label: str, lifetime: timedelta = timedelta(days=90)
    ) -> tuple[str, str]:
        identity = self._repository.identity(identity_id)
        if (
            identity is None or not identity.enabled
            or identity.kind not in (IdentityKind.SERVICE, IdentityKind.DEVICE)
        ):
            raise ValueError("Enabled service or device identity required")
        credential_id = str(uuid4())
        prefix = secrets.token_hex(6)
        token = f"fld_{prefix}_{secrets.token_urlsafe(40)}"
        now = datetime.now(UTC)
        self._repository.put_service_credential(
            {
                "credential_id": credential_id,
                "identity_id": identity_id,
                "key_prefix": prefix,
                "key_hash": hashlib.sha256(token.encode()).hexdigest(),
                "label": label.strip()[:100],
                "created_at_utc": now.isoformat(),
                "expires_at_utc": (now + lifetime).isoformat(),
            }
        )
        return credential_id, token

    def authenticate_service_key(self, token: str) -> Identity:
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != "fld":
            raise AuthenticationFailed("Service credential is invalid")
        record = self._repository.service_credential(parts[1])
        now = datetime.now(UTC).isoformat()
        if (
            record is None or record["revoked_at_utc"]
            or str(record["expires_at_utc"]) <= now
            or not hmac.compare_digest(
                str(record["key_hash"]), hashlib.sha256(token.encode()).hexdigest()
            )
        ):
            raise AuthenticationFailed("Service credential is invalid")
        identity = self._repository.identity(str(record["identity_id"]))
        if (
            identity is None or not identity.enabled
            or identity.kind not in (IdentityKind.SERVICE, IdentityKind.DEVICE)
        ):
            raise AuthenticationFailed("Machine identity is disabled")
        return identity

    def revoke_service_key(self, credential_id: str) -> None:
        self._repository.revoke_service_credential(
            credential_id, datetime.now(UTC).isoformat()
        )

    @classmethod
    def _dummy_verify(cls, password: str) -> None:
        hashlib.pbkdf2_hmac("sha256", password.encode(), b"\0" * 32, cls.ITERATIONS)
