"""WEB-045 exact Administration action capability projection."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.server.api import ApiResponse
from natureai_next.server.administration_actions_web import (
    patch_administration_actions_response,
)
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.web_capabilities import _has_authority

_ADMINISTRATION_ACTION_RULES = {
    "operator.services.enroll": ("service.enroll", "infrastructure", "administration"),
    "operator.services.activate": ("service.activate", "infrastructure", "administration"),
    "operator.services.drain": ("service.drain", "infrastructure", "administration"),
    "operator.services.stop": ("service.stop", "infrastructure", "administration"),
    "operator.services.revoke": ("service.revoke", "infrastructure", "administration"),
    "operator.storage.enable": ("storage.enable", "infrastructure", "administration"),
    "operator.storage.disable": ("storage.disable", "infrastructure", "administration"),
}
_SERVICE_OPERATIONS = ("activate", "drain", "stop", "revoke")
_STORAGE_OPERATIONS = ("enable", "disable")


class AdministrationActionsApiMixin:
    """Project exact and resource-scoped Administration action authority."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        path = urlsplit(target).path
        if method == "GET" and response.status == 200:
            if path == "/api/v1/web/capabilities":
                response = self._administration_capabilities(headers, response)
            elif path == "/api/v1/operator/overview":
                response = self._operator_action_projection(headers, response)
        return patch_administration_actions_response(target, response)

    @staticmethod
    def _routed_headers(headers: dict[str, str]) -> dict[str, str]:
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        return routed_headers

    def _administration_capabilities(
        self, headers: dict[str, str], response: ApiResponse
    ) -> ApiResponse:
        routed_headers = self._routed_headers(headers)
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return response
        payload = self._json_payload(response)
        if payload is None:
            return response
        actions = payload.get("actions")
        if not isinstance(actions, dict):
            actions = {}
            payload["actions"] = actions
        for name, rule in _ADMINISTRATION_ACTION_RULES.items():
            actions[name] = _has_authority(self, identity, rule)
        return self._replace_json(response, payload)

    def _operator_action_projection(
        self, headers: dict[str, str], response: ApiResponse
    ) -> ApiResponse:
        routed_headers = self._routed_headers(headers)
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return response
        payload = self._json_payload(response)
        if payload is None:
            return response
        services = payload.get("services")
        if isinstance(services, list):
            for service in services:
                if not isinstance(service, dict):
                    continue
                service_id = str(service.get("service_id") or "").strip()
                service["allowed_actions"] = [
                    operation
                    for operation in _SERVICE_OPERATIONS
                    if service_id
                    and self._allow_operator(
                        identity,
                        routed_headers,
                        f"service.{operation}",
                        service_id,
                    )
                ]
        archives = payload.get("linked_archives")
        if isinstance(archives, list):
            for archive in archives:
                if not isinstance(archive, dict):
                    continue
                storage_id = str(archive.get("storage_id") or "").strip()
                archive["allowed_actions"] = [
                    operation
                    for operation in _STORAGE_OPERATIONS
                    if storage_id
                    and self._allow_operator(
                        identity,
                        routed_headers,
                        f"storage.{operation}",
                        storage_id,
                    )
                ]
        return self._replace_json(response, payload)

    @staticmethod
    def _json_payload(response: ApiResponse) -> dict[str, object] | None:
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _replace_json(response: ApiResponse, payload: dict[str, object]) -> ApiResponse:
        return ApiResponse(
            response.status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            response.content_type,
            response.headers,
        )
