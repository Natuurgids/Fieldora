import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.application.governed_pack_security import (
    GovernedPackEnvelope,
    SecureGovernedPackManager,
)
from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.synchronization import EnrollmentState, PlatformAccount, ProjectEnrollment
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.governed_packs import SqliteGovernedPackRegistry
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import SqliteDesktopSynchronizationRepository


class MemoryKeys:
    def __init__(self):
        self.values = {}

    def put(self, key_ref, key):
        self.values[key_ref] = key

    def get(self, key_ref):
        return self.values[key_ref]

    def delete(self, key_ref):
        self.values.pop(key_ref, None)


def _registry(tmp_path: Path):
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.6").apply(connection)
    sync = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(sync)
    service.save_account(
        PlatformAccount("a", "https://fieldora.example", "Account", "org", "user", "now")
    )
    service.enroll_project(
        ProjectEnrollment(
            "e", "a", "p", "c", EnrollmentState.ACTIVE, ("view",),
            "2027-01-01T00:00:00+00:00", 1, "now",
        )
    )
    return SqliteGovernedPackRegistry(factory)


def test_envelope_encrypts_signs_and_enforces_expiry() -> None:
    signing = Ed25519PrivateKey.generate()
    key = os.urandom(32)
    payload = b"sensitive governed records"
    codec = GovernedPackEnvelope()
    envelope = codec.seal(
        payload, pack_id="pack", expires_at_utc="2027-01-01T00:00:00+00:00",
        signing_key_id="signing-1", content_key=key, signing_key=signing,
    )
    assert payload not in envelope
    _header, opened = codec.open(
        envelope, content_key=key, verification_key=signing.public_key(),
        at_utc="2026-08-01T00:00:00+00:00",
    )
    assert opened == payload
    try:
        codec.open(
            envelope, content_key=key, verification_key=signing.public_key(),
            at_utc="2027-01-01T00:00:00+00:00",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("expired governed pack was opened")


def test_tamper_is_rejected_and_revocation_destroys_key_and_envelope(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    keys = MemoryKeys()
    manager = SecureGovernedPackManager(tmp_path / "secure-packs", registry, keys)
    signing = Ed25519PrivateKey.generate()
    key = os.urandom(32)
    codec = GovernedPackEnvelope()
    envelope = codec.seal(
        b"payload", pack_id="pack", expires_at_utc="2027-01-01T00:00:00+00:00",
        signing_key_id="signing-1", content_key=key, signing_key=signing,
    )
    target = manager.install(
        envelope, pack_id="pack", enrollment_id="e", key_ref="key:pack",
        content_key=key, expires_at_utc="2027-01-01T00:00:00+00:00",
        signing_key_id="signing-1",
    )
    assert manager.open(
        "pack", verification_key=signing.public_key(),
        at_utc="2026-08-01T00:00:00+00:00",
    ) == b"payload"
    tampered = bytearray(envelope)
    tampered[-8] ^= 1
    try:
        codec.open(
            bytes(tampered), content_key=key, verification_key=signing.public_key(),
            at_utc="2026-08-01T00:00:00+00:00",
        )
    except (InvalidSignature, ValueError):
        pass
    else:
        raise AssertionError("tampered envelope was accepted")
    manager.revoke("pack")
    assert "key:pack" not in keys.values
    assert not target.exists()
    try:
        manager.open(
            "pack", verification_key=signing.public_key(),
            at_utc="2026-08-01T00:00:00+00:00",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("revoked governed pack was opened")
