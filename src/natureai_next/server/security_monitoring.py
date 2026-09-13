"""Bounded security-monitoring events for trusted-side package collection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Protocol

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SecurityMonitoringSink(Protocol):
    """Destination for bounded security events such as a SIEM or monitoring host."""

    def emit_security_event(self, event: dict[str, str]) -> None:
        """Emit one bounded security event."""


@dataclass(frozen=True, slots=True)
class PackageIntegrityAlert:
    event_type: str
    severity: str
    request_id: str
    package_id: str
    broadcast_id: str
    collector_id: str
    expected_sha256: str
    observed_sha256: str
    signing_key_id: str
    package_class: str
    artifact_id: str
    version: str
    provenance: str
    signature_verified: str

    def as_event(self) -> dict[str, str]:
        return asdict(self)


def verify_collected_package_integrity(
    *,
    expected_sha256: str,
    observed_sha256: str,
    request_id: str,
    package_id: str,
    broadcast_id: str,
    collector_id: str,
    signing_key_id: str,
    package_class: str,
    artifact_id: str,
    version: str,
    provenance: str,
    signature_verified: bool,
    sink: SecurityMonitoringSink | None = None,
) -> bool:
    """Fail closed on a collected-package digest mismatch and emit a bounded alert."""
    if not _SHA256_RE.fullmatch(expected_sha256) or not _SHA256_RE.fullmatch(observed_sha256):
        raise ValueError("package digests must be lowercase SHA-256 values")
    if expected_sha256 == observed_sha256:
        return True

    alert = PackageIntegrityAlert(
        event_type="package_integrity_mismatch",
        severity="high",
        request_id=request_id,
        package_id=package_id,
        broadcast_id=broadcast_id,
        collector_id=collector_id,
        expected_sha256=expected_sha256,
        observed_sha256=observed_sha256,
        signing_key_id=signing_key_id,
        package_class=package_class,
        artifact_id=artifact_id,
        version=version,
        provenance=provenance,
        signature_verified="true" if signature_verified else "false",
    )
    if sink is not None:
        sink.emit_security_event(alert.as_event())
    return False
