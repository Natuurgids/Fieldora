"""Composition wrapper for the governed Fieldora Platform server.

The established reference server remains the authentication, PBAC, persistence, job,
and transport composition. This wrapper replaces only deliberate extension points and
bootstraps explicit privileges for the first clean-install administrator.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from natureai_next.domain.access_control import PolicyEffect, PolicySource
from natureai_next.server.facility_platform_api import CompletePlatformFieldoraApi
from natureai_next.server.platform_extensions import ProjectOptionalStagedIngestionStore


_LAST_REPOSITORY: Any = None
_LAST_IDENTITY: Any = None


def main(argv: Sequence[str] | None = None) -> int:
    from natureai_next.bootstrap import server_cli

    arguments = list(sys.argv[1:] if argv is None else argv)
    if "register-media" in arguments and "--project" not in arguments:
        arguments.extend(("--project", ""))

    base_administration = server_cli.AccessAdministrationService

    class TrackingAdministration(base_administration):
        def __init__(self, repository: Any) -> None:
            global _LAST_REPOSITORY
            _LAST_REPOSITORY = repository
            super().__init__(repository)

        def create_identity(self, *args: Any, **kwargs: Any):
            global _LAST_IDENTITY
            identity = super().create_identity(*args, **kwargs)
            _LAST_IDENTITY = identity
            return identity

    server_cli.FieldoraApi = CompletePlatformFieldoraApi
    server_cli.StagedIngestionStore = ProjectOptionalStagedIngestionStore
    server_cli.AccessAdministrationService = TrackingAdministration
    try:
        result = server_cli.main(arguments)
    finally:
        server_cli.FieldoraApi = CompletePlatformFieldoraApi
        server_cli.StagedIngestionStore = ProjectOptionalStagedIngestionStore
        server_cli.AccessAdministrationService = base_administration

    if result == 0 and "init-user" in arguments:
        _bootstrap_initial_operator(base_administration)
    return result


def _bootstrap_initial_operator(administration_type: Any) -> None:
    if _LAST_REPOSITORY is None or _LAST_IDENTITY is None:
        raise RuntimeError("initial administrator bootstrap identity was not captured")
    administration = administration_type(_LAST_REPOSITORY)
    identity = _LAST_IDENTITY
    organization_id = identity.organization_id
    administration.grant_role(identity.identity_id, "platform-operator", organization_id)
    administration.create_policy(
        name="Initial governed evidence and scientific collaboration",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="project-manager",
        actions=(
            "view",
            "download",
            "upload",
            "search",
            "submit_evidence",
            "view_submission",
            "request_review",
            "view_review",
            "determine",
            "accept_determination",
        ),
        resource_types=("asset", "submission", "review_case"),
        organization_id=organization_id,
        purposes=("research",),
    )
    administration.create_policy(
        name="Initial facilities planning and relocation access",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="project-manager",
        actions=("view", "create", "edit", "update"),
        resource_types=(
            "operations.drawing",
            "operations.layout",
            "operations.relocation",
        ),
        organization_id=organization_id,
        purposes=("operations",),
    )
    administration.create_policy(
        name="Initial Fieldora infrastructure operator",
        effect=PolicyEffect.ALLOW,
        source=PolicySource.ROLE,
        role_id="platform-operator",
        actions=(
            "infrastructure.view",
            "service.enroll",
            "service.heartbeat",
            "service.activate",
            "service.drain",
            "service.stop",
            "service.revoke",
        ),
        resource_types=("infrastructure",),
        organization_id=organization_id,
        purposes=("administration",),
    )


if __name__ == "__main__":
    raise SystemExit(main())
