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


class AdministrationActionsApiMixin:
    """Add exact Administration action booleans to the existing capability response."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if (
            method == "GET"
            and urlsplit(target).path == "/api/v1/web/capabilities"
            and response.status == 200
        ):
            response = self._administration_capabilities(headers, response)
        return patch_administration_actions_response(target, response)

    def _administration_capabilities(
        self, headers: dict[str, str], response: ApiResponse
    ) -> ApiResponse:
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return response
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return response
        if not isinstance(payload, dict):
            return response
        actions = payload.get("actions")
        if not isinstance(actions, dict):
            actions = {}
            payload["actions"] = actions
        for name, rule in _ADMINISTRATION_ACTION_RULES.items():
            actions[name] = _has_authority(self, identity, rule)
        return ApiResponse(
            response.status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
            response.content_type,
            response.headers,
        )
