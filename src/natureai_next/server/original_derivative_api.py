"""Governed original/derivative lineage for managed Library media.

Derivatives are separate scientific artifacts. Registration records lineage to the
current governed original identity and checksum; it never rewrites the canonical
MediaRecord or its byte instance. Internal derivative storage locations are not part
of the browser contract.
"""

from __future__ import annotations

import json
import time
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.original_derivative_web import patch_original_derivative_response

_DERIVATIVES = "server_media_derivatives"
_DERIVATIVE_KINDS = {"thumbnail", "preview", "transcode", "analysis"}
_PROTECTED_FIELDS = {
    "id",
    "derivative_id",
    "source_media_id",
    "organization_id",
    "source_sha256",
    "created_by_identity_id",
    "created_at_us",
}
_GATE_PATH = "/api/v1/__original_derivative_governance_gate__"


class OriginalDerivativeApiMixin:
    """Expose derivative lineage without allowing derivative/original conflation."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        derivative_media_id = self._derivative_media_id(route.path)
        detail_media_id = self._detail_media_id(route.path)

        if derivative_media_id and method in {"GET", "POST"}:
            response = self._derivative_response(
                method, derivative_media_id, headers, body
            )
            return patch_original_derivative_response(target, response)

        response = super().dispatch(method, target, headers, body)
        if detail_media_id and method == "GET" and response.status == 200:
            response = self._decorate_media_detail(
                detail_media_id, headers, response
            )
        return patch_original_derivative_response(target, response)

    @staticmethod
    def _derivative_media_id(path: str) -> str:
        prefix = "/api/v1/media/"
        suffix = "/derivatives"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return ""
        media_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        return media_id if media_id and "/" not in media_id else ""

    @staticmethod
    def _detail_media_id(path: str) -> str:
        prefix = "/api/v1/media/"
        suffix = "/detail"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return ""
        media_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        return media_id if media_id and "/" not in media_id else ""

    def _derivative_response(
        self,
        method: str,
        media_id: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        routed_headers = self._derivative_headers(headers)
        gate = super().dispatch("DELETE", _GATE_PATH, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})

        original = self._media.record(media_id)
        if original is None or original.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        action = "view" if method == "GET" else "derive"
        if not self._derivative_allowed(identity, routed_headers, action, original):
            return ApiResponse.json(
                404 if method == "GET" else 403,
                {"error": "not_found" if method == "GET" else "forbidden"},
            )
        if method == "GET":
            return ApiResponse.json(
                200,
                {
                    "source": self._original_payload(original),
                    "items": self._derivatives_for(
                        media_id, identity.organization_id
                    ),
                    "original_mutated": False,
                },
            )
        return self._register_derivative(identity, routed_headers, original, body)

    def _register_derivative(self, identity, headers, original, body: bytes) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            value = json.loads(body)
            if not isinstance(value, dict) or _PROTECTED_FIELDS.intersection(value):
                raise ValueError("protected derivative field")
            kind = self._required_text(value, "kind")
            if kind not in _DERIVATIVE_KINDS:
                raise ValueError("unsupported derivative kind")
            mime_type = self._required_text(value, "mime_type")[:200]
            sha256 = self._sha256(value.get("sha256"))
            source_sha256 = self._sha256(value.get("source_sha256"))
            size_bytes = int(value.get("size_bytes", 0))
            if size_bytes <= 0:
                raise ValueError("invalid derivative size")
            label = str(value.get("label", "")).strip()[:200]
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_derivative"})

        if source_sha256 != original.sha256:
            return ApiResponse.json(409, {"error": "original_identity_changed"})

        now_us = int(time.time() * 1_000_000)
        record = {
            "id": str(uuid4()),
            "source_media_id": original.media_id,
            "organization_id": original.organization_id,
            "project_id": original.project_id,
            "kind": kind,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "source_sha256": original.sha256,
            "label": label,
            "created_by_identity_id": identity.identity_id,
            "created_at_us": now_us,
        }
        try:
            self._science.put(_DERIVATIVES, record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            201,
            {
                "item": self._public_derivative(record),
                "source": self._original_payload(original),
                "original_mutated": False,
            },
        )

    def _decorate_media_detail(
        self, media_id: str, headers: dict[str, str], response: ApiResponse
    ) -> ApiResponse:
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return response
        if not isinstance(payload, dict) or not isinstance(payload.get("item"), dict):
            return response
        item = payload["item"]
        original = self._media.record(media_id) if self._media is not None else None
        if original is None:
            return response
        routed_headers = self._derivative_headers(headers)
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return response
        if original.organization_id != identity.organization_id:
            return response
        item["artifact_role"] = "governed_original"
        payload["derivatives"] = self._derivatives_for(
            media_id, identity.organization_id
        )
        payload["derivative_contract"] = {
            "original_authoritative": True,
            "derivatives_replace_original": False,
            "lineage_hash": original.sha256,
        }
        return ApiResponse.json(200, payload)

    def _derivatives_for(self, media_id: str, organization_id: str) -> list[dict]:
        return [
            self._public_derivative(record)
            for record in self._science.records(_DERIVATIVES)
            if str(record.get("source_media_id", "")) == media_id
            and str(record.get("organization_id", "")) == organization_id
        ]

    def _derivative_allowed(self, identity, headers, action: str, original) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "asset",
                original.media_id,
                original.organization_id,
                original.project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        ).allowed

    @staticmethod
    def _original_payload(original) -> dict[str, object]:
        return {
            "media_id": original.media_id,
            "artifact_role": "governed_original",
            "mime_type": original.mime_type,
            "size_bytes": original.size_bytes,
            "sha256": original.sha256,
        }

    @staticmethod
    def _public_derivative(record: dict) -> dict:
        return {
            "derivative_id": str(record.get("id", "")),
            "source_media_id": str(record.get("source_media_id", "")),
            "kind": str(record.get("kind", "")),
            "mime_type": str(record.get("mime_type", "")),
            "size_bytes": int(record.get("size_bytes", 0)),
            "sha256": str(record.get("sha256", "")),
            "source_sha256": str(record.get("source_sha256", "")),
            "label": str(record.get("label", "")),
            "created_at_us": int(record.get("created_at_us", 0)),
        }

    @staticmethod
    def _sha256(value) -> str:
        digest = str(value or "").strip().casefold()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid sha256")
        return digest

    @staticmethod
    def _required_text(data: dict, field: str) -> str:
        value = str(data.get(field, "")).strip()
        if not value:
            raise ValueError(f"{field} is required")
        return value

    @staticmethod
    def _derivative_headers(headers: dict[str, str]) -> dict[str, str]:
        routed = dict(headers)
        if routed.get("authorization"):
            return routed
        cookie = SimpleCookie()
        try:
            cookie.load(routed.get("cookie", ""))
        except Exception:
            return routed
        morsel = cookie.get("fieldora_session")
        if morsel is not None and morsel.value:
            routed["authorization"] = f"Bearer {morsel.value}"
        return routed
