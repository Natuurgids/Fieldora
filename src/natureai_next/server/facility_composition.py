"""Authenticated composition for facility/mobile HTTP routes.

Facility routes deliberately pass through the existing :class:`FieldoraApi`
first.  That preserves the server's single authentication, session and tenant
quota path.  Only the authenticated ``404`` for the otherwise-unknown facility
namespace is replaced by the facility adapter response.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse, FieldoraApi
from natureai_next.server.facility_api import FacilityApiAdapter


class _IdentityLike(Protocol):
    identity_id: str


class FacilityEnabledApi:
    """Compose facility routes behind the existing authenticated API boundary."""

    def __init__(self, base: FieldoraApi, facility: FacilityApiAdapter) -> None:
        self.base = base
        self.facility = facility

    def dispatch(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        path = urlsplit(target).path
        if not path.startswith(self.facility.PREFIX):
            return self.base.dispatch(method, target, headers, body)

        # The base API owns authentication/session validation and tenant quota.
        # For this namespace it has no route of its own, so an authenticated
        # request reaches its normal 404 while authentication/quota failures are
        # returned unchanged here.
        gate = self.base.dispatch(method, target, headers, body)
        if gate.status != 404:
            return gate

        # Authentication has already succeeded above.  Re-resolving the same
        # identity is read-only and avoids introducing a second auth policy.
        _token, identity = self.base._identity(headers)
        payload = self._json_body(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_json"})
        result = self.facility.dispatch(
            method,
            path,
            actor=str(identity.identity_id),
            body=payload,
        )
        if result is None:
            return gate
        return ApiResponse.json(result.status, result.payload)

    @staticmethod
    def _json_body(body: bytes) -> Mapping[str, Any] | None:
        if not body:
            return {}
        if len(body) > 64 * 1024:
            return None
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None
