"""Operator-lifecycle gate for the managed Fieldora API service."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_platform_api import CompletePlatformFieldoraApi
from natureai_next.server.operator_control import ServiceState


class RuntimeGovernedFieldoraApi(CompletePlatformFieldoraApi):
    """Keep a long-lived API process warm while respecting drain/revocation state."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        service_id = os.environ.get("FIELDORA_SERVICE_ID", "").strip()
        if service_id:
            record = self._operator.service(service_id)
            state = ServiceState.REVOKED if record is None else ServiceState(record.state)
            if path in {"/api/v1/health/live", "/api/v1/status"}:
                return super().dispatch(method, target, headers, body)
            if path == "/api/v1/health/ready" and state is not ServiceState.ACTIVE:
                return ApiResponse.json(
                    503,
                    {
                        "ready": False,
                        "service_id": service_id,
                        "service_state": state.value,
                        "detail": "service is not active",
                    },
                )
            if path.startswith("/api/v1/operator"):
                # Operators must retain a route to reactivate or inspect a drained node.
                return super().dispatch(method, target, headers, body)
            if state is not ServiceState.ACTIVE:
                return ApiResponse.json(
                    503,
                    {
                        "error": "service_unavailable",
                        "service_id": service_id,
                        "service_state": state.value,
                    },
                )
        return super().dispatch(method, target, headers, body)
