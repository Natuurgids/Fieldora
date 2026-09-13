"""Trusted application boundary for Security Install acceptance.

This module is the only production bridge between provider-neutral Security
Install evidence and Fieldora business authorization. Callers provide identity
and release binding, never an ``AccessDecision``. The decision is always made
and audited by Fieldora's normal PBAC service.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from natureai_next.application.access_control import AccessDenied, PolicyDecisionService
from natureai_next.domain.access_control import AccessRequest
from natureai_next.domain.security_install import (
    SecurityInstallAcceptanceError,
    TrustedInstallAcceptance,
    accept_security_install_release,
)
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository

SECURITY_INSTALL_ACTION = "install"
SECURITY_INSTALL_RESOURCE_TYPE = "security_install_release"
SECURITY_INSTALL_PURPOSE = "security_install"


def require_security_install(
    evidence: Mapping[str, object],
    *,
    artifact_path: Path,
    access_control_database: Path,
    subject_id: str,
    expected_package_id: str,
    expected_target_component: str,
    actual_target_version: str,
) -> TrustedInstallAcceptance:
    """Require audited PBAC and independently accept one local release artifact."""
    if not isinstance(evidence, Mapping):
        raise SecurityInstallAcceptanceError("trusted Security Install evidence must be an object")

    subject = subject_id.strip()
    if not subject:
        raise SecurityInstallAcceptanceError("missing Fieldora security-install subject")
    package_id = expected_package_id.strip()
    component = expected_target_component.strip()
    target_version = actual_target_version.strip()
    if not package_id or not component or not target_version:
        raise SecurityInstallAcceptanceError("incomplete Security Install release binding")

    repository = SqliteAccessControlRepository(access_control_database)
    policy = PolicyDecisionService(repository)
    request = AccessRequest(
        subject_id=subject,
        action=SECURITY_INSTALL_ACTION,
        resource_type=SECURITY_INSTALL_RESOURCE_TYPE,
        resource_id=package_id,
        purpose=SECURITY_INSTALL_PURPOSE,
        attributes={"target_component": component, "actual_target_version": target_version},
    )
    try:
        decision = policy.require(request)
    except AccessDenied as exc:
        raise SecurityInstallAcceptanceError(
            f"Fieldora business authorization denied: {exc}"
        ) from exc

    return accept_security_install_release(
        evidence,
        artifact_path=artifact_path,
        expected_package_id=package_id,
        expected_target_component=component,
        actual_target_version=target_version,
        business_authorization=decision,
    )
