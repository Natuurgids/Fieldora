"""Governed managed-web Knowledge proposal and review parity.

Knowledge is not a generic mutable record. A proposal is immutable scientific input
with preserved producer/source provenance; review is an explicit, revisioned action;
acceptance creates a separate canonical conclusion that traces back to both proposal
and acceptance action.
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
from natureai_next.server.knowledge_review_web import (
    patch_knowledge_review_web_response,
)

_PROPOSALS = "server_knowledge_proposals"
_ACTIONS = "server_knowledge_review_actions"
_CANONICAL = "server_knowledge_canonical"
_REVIEW_ACTIONS = {"accept", "reject", "defer"}
_PROTECTED_CREATE_FIELDS = {
    "id",
    "revision",
    "review_state",
    "review_actions",
    "canonical",
    "canonical_id",
    "source_suggestion_public_id",
    "acceptance_action_public_id",
    "created_at_us",
    "updated_at_us",
}
_GATE_PATH = "/api/v1/__knowledge_governance_gate__"


class KnowledgeParityApiMixin:
    """Own managed Knowledge reads, creation, and review before the generic API."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        collection = path == "/api/v1/knowledge"
        prefix = "/api/v1/knowledge/"
        tail = path.removeprefix(prefix).strip("/") if path.startswith(prefix) else ""
        parts = tuple(part for part in tail.split("/") if part)
        item = len(parts) == 1
        review = len(parts) == 2 and parts[1] == "review"
        governed = collection or item or review
        supported = (
            (collection and method in {"GET", "POST"})
            or (item and method in {"GET", "PUT", "PATCH", "DELETE"})
            or (review and method == "POST")
        )
        if not governed or not supported:
            response = super().dispatch(method, target, headers, body)
            return patch_knowledge_review_web_response(target, response)

        routed_headers = self._knowledge_headers(headers)
        # Exercise the established managed lifecycle/session gates on a deliberately
        # unsupported route. Never probe the real Knowledge path: the generic API
        # owns that legacy path and a DELETE probe could mutate its collection.
        gate = super().dispatch("DELETE", _GATE_PATH, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})

        if collection and method == "GET":
            return self._list_knowledge_proposals(identity, routed_headers)
        if collection and method == "POST":
            return self._create_knowledge_proposal(identity, routed_headers, body)
        proposal_id = unquote(parts[0]) if parts else ""
        if item and method == "GET":
            return self._get_knowledge_proposal(proposal_id, identity, routed_headers)
        if item:
            return ApiResponse.json(405, {"error": "knowledge_review_action_required"})
        return self._review_knowledge_proposal(
            proposal_id, identity, routed_headers, body
        )

    def _list_knowledge_proposals(self, identity, headers) -> ApiResponse:
        items: list[dict] = []
        for raw in self._science.records(_PROPOSALS):
            item = dict(raw)
            if self._knowledge_allowed(
                identity,
                headers,
                "view",
                str(item.get("id", "")),
                str(item.get("project_id", "")),
            ):
                items.append(item)
        return ApiResponse.json(200, {"items": items})

    def _get_knowledge_proposal(
        self, proposal_id: str, identity, headers
    ) -> ApiResponse:
        current = self._current_knowledge_proposal(proposal_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if not self._knowledge_allowed(
            identity,
            headers,
            "view",
            proposal_id,
            str(current.get("project_id", "")),
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(
            200, {"item": current, "revision": int(current.get("revision", 1))}
        )

    def _create_knowledge_proposal(self, identity, headers, body: bytes) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = self._json_object(body)
            if _PROTECTED_CREATE_FIELDS.intersection(data):
                raise ValueError("protected field")
            project_id = self._required_text(data, "project_id")
            subject = data.get("subject")
            candidate = data.get("candidate")
            source_snapshot = data.get("source_snapshot")
            if not isinstance(subject, dict) or not isinstance(candidate, dict):
                raise ValueError("subject and candidate are required")
            if not isinstance(source_snapshot, dict):
                raise ValueError("source snapshot is required")
            provider_key = self._required_text(source_snapshot, "provider_key")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_knowledge_proposal"})

        proposal_id = str(uuid4())
        if not self._knowledge_allowed(
            identity, headers, "edit", proposal_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        now_us = int(time.time() * 1_000_000)
        record = {
            "id": proposal_id,
            "project_id": project_id,
            "subject": subject,
            "candidate": candidate,
            "source_snapshot": source_snapshot,
            "provider_key": provider_key,
            "review_state": "pending",
            "review_actions": [],
            "canonical": None,
            "created_at_us": now_us,
            "updated_at_us": now_us,
            "revision": 1,
        }
        try:
            revision = self._science.put(_PROPOSALS, record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(201, {"item": record, "revision": revision})

    def _review_knowledge_proposal(
        self, proposal_id: str, identity, headers, body: bytes
    ) -> ApiResponse:
        expected = self._knowledge_expected_revision(headers)
        if isinstance(expected, ApiResponse):
            return expected
        try:
            data = self._json_object(body)
            if set(data) != {"action"}:
                raise ValueError("review action only")
            action = self._required_text(data, "action")
            if action not in _REVIEW_ACTIONS:
                raise ValueError("unsupported action")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_review_action"})

        current = self._current_knowledge_proposal(proposal_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if int(current.get("revision", 0)) != expected:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        project_id = str(current.get("project_id", ""))
        if not self._knowledge_allowed(
            identity, headers, "edit", proposal_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        state = str(current.get("review_state", "pending"))
        if state not in {"pending", "deferred"}:
            return ApiResponse.json(
                409, {"error": "knowledge_review_already_resolved"}
            )

        action_id = str(uuid4())
        now_us = int(time.time() * 1_000_000)
        next_state = {
            "accept": "accepted",
            "reject": "rejected",
            "defer": "deferred",
        }[action]
        action_record = {
            "id": action_id,
            "proposal_id": proposal_id,
            "project_id": project_id,
            "action": action,
            "from_state": state,
            "to_state": next_state,
            "actor_identity_id": identity.identity_id,
            "created_at_us": now_us,
        }
        try:
            self._science.put(_ACTIONS, action_record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})

        updated = dict(current)
        updated["review_state"] = next_state
        updated["review_actions"] = [
            *list(current.get("review_actions", [])),
            action_record,
        ]
        canonical = None
        if action == "accept":
            canonical = {
                "id": str(uuid4()),
                "project_id": project_id,
                "subject": current["subject"],
                "candidate": current["candidate"],
                "source_snapshot": current["source_snapshot"],
                "provider_key": current["provider_key"],
                "lifecycle_state": "accepted",
                "source_suggestion_public_id": proposal_id,
                "acceptance_action_public_id": action_id,
                "created_at_us": now_us,
            }
            try:
                self._science.put(_CANONICAL, canonical, 0)
            except ValueError:
                return ApiResponse.json(409, {"error": "revision_conflict"})
            updated["canonical"] = canonical
        updated["updated_at_us"] = now_us
        updated["revision"] = expected + 1
        try:
            revision = self._science.put(_PROPOSALS, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            200,
            {
                "item": updated,
                "revision": revision,
                "action": action_record,
                "canonical": canonical,
            },
        )

    def _current_knowledge_proposal(self, proposal_id: str) -> dict | None:
        return next(
            (
                dict(item)
                for item in self._science.records(_PROPOSALS)
                if str(item.get("id", "")) == proposal_id
            ),
            None,
        )

    def _knowledge_allowed(
        self, identity, headers, action, resource_id, project_id
    ) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "knowledge",
                resource_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        ).allowed

    @staticmethod
    def _knowledge_expected_revision(headers: dict[str, str]) -> int | ApiResponse:
        expected = headers.get("if-match")
        if expected is None:
            return ApiResponse.json(428, {"error": "revision_required"})
        try:
            revision = int(expected)
            if revision < 1:
                raise ValueError
        except (TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_review_action"})
        return revision

    @staticmethod
    def _knowledge_headers(headers: dict[str, str]) -> dict[str, str]:
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

    @staticmethod
    def _json_object(body: bytes) -> dict:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError("JSON object required")
        return value

    @staticmethod
    def _required_text(data: dict, field: str) -> str:
        value = str(data.get(field, "")).strip()
        if not value:
            raise ValueError(f"{field} is required")
        return value
