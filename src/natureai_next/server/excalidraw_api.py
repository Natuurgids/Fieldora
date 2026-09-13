"""Governed Excalidraw document and collaboration adapter.

Excalidraw remains an independent editor. Fieldora owns only the project-scoped
container, authorization, revision coordination, and audit-relevant metadata.
There are deliberately no anonymous rooms, public share tokens, or external
collaboration endpoints in this adapter.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest, Identity
from natureai_next.server.api import ApiResponse

_MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_COLLECTION = "excalidraw_boards"


class ExcalidrawApiMixin:
    """Project-governed storage and revision sync for Excalidraw documents."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if not route.path.startswith("/api/v1/excalidraw/"):
            return super().dispatch(method, target, headers, body)

        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})

        if route.path == "/api/v1/excalidraw/boards":
            if method == "GET":
                return self._excalidraw_list(route.query, headers, identity)
            if method == "POST":
                return self._excalidraw_create(headers, body, identity)
            return ApiResponse.json(405, {"error": "method_not_allowed"})

        suffix = route.path.removeprefix("/api/v1/excalidraw/boards/")
        collaboration = suffix.endswith("/collaboration")
        board_id = suffix.removesuffix("/collaboration") if collaboration else suffix
        if not board_id or "/" in board_id:
            return ApiResponse.json(404, {"error": "not_found"})

        board = self._excalidraw_board(board_id, identity.organization_id)
        if board is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(board.get("project_id") or "")

        if collaboration:
            if method != "GET":
                return ApiResponse.json(405, {"error": "method_not_allowed"})
            if not self._excalidraw_allowed(identity, headers, project_id, "view"):
                return ApiResponse.json(403, {"error": "forbidden"})
            query = parse_qs(route.query)
            try:
                since = max(0, int(query.get("since", ["0"])[0]))
            except ValueError:
                return ApiResponse.json(400, {"error": "invalid_revision"})
            revision = int(board.get("revision") or 0)
            return ApiResponse.json(
                200,
                {
                    "board_id": board_id,
                    "revision": revision,
                    "changed": revision > since,
                    "board": board if revision > since else None,
                    "transport": "authenticated-revision-sync",
                },
            )

        if method == "GET":
            if not self._excalidraw_allowed(identity, headers, project_id, "view"):
                return ApiResponse.json(403, {"error": "forbidden"})
            return ApiResponse.json(200, {"item": board, "revision": board["revision"]})
        if method == "PUT":
            if not self._excalidraw_allowed(identity, headers, project_id, "edit"):
                return ApiResponse.json(403, {"error": "forbidden"})
            return self._excalidraw_update(board, headers, body, identity)
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    def _excalidraw_list(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        project_id = parse_qs(query_string).get("project_id", [""])[0].strip()
        if not project_id:
            return ApiResponse.json(400, {"error": "project_id_required"})
        if not self._excalidraw_allowed(identity, headers, project_id, "view"):
            return ApiResponse.json(403, {"error": "forbidden"})
        items = []
        for board in self._science.records(_COLLECTION):
            if (
                str(board.get("organization_id") or "") == identity.organization_id
                and str(board.get("project_id") or "") == project_id
                and not bool(board.get("archived"))
            ):
                items.append(self._excalidraw_summary(board))
        items.sort(key=lambda item: (str(item.get("title") or "").casefold(), item["id"]))
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _excalidraw_create(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if len(body) > _MAX_DOCUMENT_BYTES:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = json.loads(body)
            project_id = str(data["project_id"]).strip()
            title = str(data.get("title") or "Untitled whiteboard").strip()
            scene = self._excalidraw_scene(data.get("scene", {}))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        if not project_id or not title:
            return ApiResponse.json(400, {"error": "invalid_request"})
        if not self._excalidraw_allowed(identity, headers, project_id, "edit"):
            return ApiResponse.json(403, {"error": "forbidden"})

        now = int(time.time())
        board_id = str(uuid.uuid4())
        board = {
            "id": board_id,
            "project_id": project_id,
            "organization_id": identity.organization_id,
            "title": title,
            "format": "excalidraw",
            "scene": scene,
            "revision": 1,
            "created_at_epoch": now,
            "updated_at_epoch": now,
            "created_by": identity.identity_id,
            "updated_by": identity.identity_id,
            "archived": False,
        }
        try:
            storage_revision = self._science.put(_COLLECTION, board, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            201, {"item": board, "revision": storage_revision, "collaboration": "internal"}
        )

    def _excalidraw_update(
        self,
        current: dict[str, Any],
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        if len(body) > _MAX_DOCUMENT_BYTES:
            return ApiResponse.json(413, {"error": "request_too_large"})
        expected_header = headers.get("if-match", "").strip().strip('"')
        try:
            expected = int(expected_header)
        except ValueError:
            return ApiResponse.json(428, {"error": "revision_required"})
        if expected < 1 or expected != int(current.get("revision") or 0):
            return ApiResponse.json(409, {"error": "revision_conflict"})
        try:
            data = json.loads(body)
            scene = self._excalidraw_scene(data.get("scene", current.get("scene", {})))
            title = str(data.get("title", current.get("title") or "Untitled whiteboard")).strip()
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        if not title:
            return ApiResponse.json(400, {"error": "invalid_request"})
        updated = dict(current)
        updated.update(
            {
                "title": title,
                "scene": scene,
                "revision": expected + 1,
                "updated_at_epoch": int(time.time()),
                "updated_by": identity.identity_id,
            }
        )
        try:
            storage_revision = self._science.put(_COLLECTION, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": updated, "revision": storage_revision})

    def _excalidraw_board(
        self, board_id: str, organization_id: str
    ) -> dict[str, Any] | None:
        for board in self._science.records(_COLLECTION):
            if (
                str(board.get("id") or "") == board_id
                and str(board.get("organization_id") or "") == organization_id
                and not bool(board.get("archived"))
            ):
                return dict(board)
        return None

    def _excalidraw_allowed(
        self,
        identity: Identity,
        headers: dict[str, str],
        project_id: str,
        action: str,
    ) -> bool:
        if not project_id:
            return False
        decision = self._decisions.decide(
            AccessRequest(
                subject_id=identity.identity_id,
                action=action,
                resource_type="project",
                resource_id=project_id,
                organization_id=identity.organization_id,
                project_id=project_id,
                purpose=headers.get("x-fieldora-purpose", "research"),
            )
        )
        return bool(decision.allowed)

    @staticmethod
    def _excalidraw_scene(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("scene must be an object")
        elements = value.get("elements", [])
        app_state = value.get("appState", {})
        files = value.get("files", {})
        if not isinstance(elements, list) or not isinstance(app_state, dict) or not isinstance(files, dict):
            raise ValueError("invalid Excalidraw scene")
        # Keep the upstream open document representation opaque. Fieldora does not
        # interpret Excalidraw element internals or make them domain dependencies.
        return {"elements": elements, "appState": app_state, "files": files}

    @staticmethod
    def _excalidraw_summary(board: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(board.get("id") or ""),
            "project_id": str(board.get("project_id") or ""),
            "title": str(board.get("title") or "Untitled whiteboard"),
            "revision": int(board.get("revision") or 0),
            "updated_at_epoch": int(board.get("updated_at_epoch") or 0),
            "updated_by": str(board.get("updated_by") or ""),
            "format": "excalidraw",
        }
