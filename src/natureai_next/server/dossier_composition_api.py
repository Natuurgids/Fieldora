"""Governed Dossier master-composition routes.

A master dossier owns only relationship records. Child dossiers remain independent governed
records and keep their own Project, review, evidence, and ownership state.
"""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.domain.science import ScienceRevisionConflict
from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_composition_web import patch_dossier_composition_response


class DossierCompositionApiMixin:
    """Expose explicit master-dossier composition without nesting child state."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        parsed = self._dossier_composition_route(route.path)
        if parsed is None:
            response = super().dispatch(method, target, headers, body)
            return patch_dossier_composition_response(target, response)

        master_id, child_id = parsed
        if not child_id and method == "GET":
            return self._dossier_composition(master_id, headers)
        if not child_id and method == "POST":
            return self._add_dossier_child(master_id, headers, body)
        if child_id and method == "DELETE":
            return self._remove_dossier_child(master_id, child_id, headers)
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    @staticmethod
    def _dossier_composition_route(path: str) -> tuple[str, str] | None:
        prefix = "/api/v1/dossiers/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) == 2 and parts[1] == "composition":
            master_id = unquote(parts[0]).strip()
            if master_id and "/" not in master_id:
                return master_id, ""
            return None
        if len(parts) == 3 and parts[1] == "composition":
            master_id = unquote(parts[0]).strip()
            child_id = unquote(parts[2]).strip()
            if master_id and child_id and "/" not in master_id and "/" not in child_id:
                return master_id, child_id
        return None

    @staticmethod
    def _same_organization(record: dict[str, object], organization_id: str) -> bool:
        return str(record.get("organization_id", "")).strip() in {"", organization_id}

    @staticmethod
    def _dossier_projection(record: dict[str, object]) -> dict[str, object]:
        return {
            "id": str(record.get("id", "")).strip(),
            "name": str(record.get("name", record.get("title", ""))).strip(),
            "title": str(record.get("title", record.get("name", ""))).strip(),
            "project_id": str(record.get("project_id", "")).strip(),
            "description": str(
                record.get("description", record.get("notes", ""))
            ).strip(),
            "dossier_type": str(record.get("dossier_type", "dossier")).strip()
            or "dossier",
            "review_status": str(
                record.get("review_status", record.get("status", "draft"))
            ).strip()
            or "draft",
        }

    def _composition_allowed(
        self,
        identity,
        action: str,
        dossier: dict[str, object],
        headers: dict[str, str],
    ) -> bool:
        dossier_id = str(dossier.get("id", "")).strip()
        project_id = str(dossier.get("project_id", "")).strip()
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "dossier",
                dossier_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        ).allowed

    def _composition_context(
        self,
        master_id: str,
        headers: dict[str, str],
        *,
        action: str,
    ):
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return None, None, None, None
        snapshot, revision = self._science.load_snapshot()
        master = next(
            (
                record
                for record in snapshot.get("dossiers", [])
                if str(record.get("id", "")).strip() == master_id
                and self._same_organization(record, identity.organization_id)
            ),
            None,
        )
        if master is None:
            return identity, snapshot, revision, None
        if not self._composition_allowed(identity, action, master, headers):
            return identity, snapshot, revision, None
        return identity, snapshot, revision, master

    def _composition_item(
        self,
        identity,
        snapshot: dict[str, object],
        master: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, object]:
        master_id = str(master.get("id", "")).strip()
        is_master = str(master.get("dossier_type", "dossier")).strip() == "master"
        links = [
            link
            for link in snapshot.get("dossier_links", [])
            if str(link.get("parent_dossier_id", "")).strip() == master_id
            and str(link.get("relationship", "contains")).strip() == "contains"
        ]
        linked_ids = {
            str(link.get("child_dossier_id", "")).strip()
            for link in links
            if str(link.get("child_dossier_id", "")).strip()
        }
        dossiers = [
            record
            for record in snapshot.get("dossiers", [])
            if self._same_organization(record, identity.organization_id)
        ]
        by_id = {
            str(record.get("id", "")).strip(): record
            for record in dossiers
            if str(record.get("id", "")).strip()
        }

        children: list[dict[str, object]] = []
        for link in links:
            child_id = str(link.get("child_dossier_id", "")).strip()
            child = by_id.get(child_id)
            if child is None or not self._composition_allowed(
                identity, "view", child, headers
            ):
                continue
            item = self._dossier_projection(child)
            item["relationship_id"] = str(link.get("id", "")).strip()
            children.append(item)

        candidates: list[dict[str, object]] = []
        if is_master:
            for child_id, child in by_id.items():
                if child_id == master_id or child_id in linked_ids:
                    continue
                if not self._composition_allowed(identity, "view", child, headers):
                    continue
                candidates.append(self._dossier_projection(child))

        return {
            "master": self._dossier_projection(master),
            "is_master": is_master,
            "children": children,
            "available_children": candidates,
        }

    def _dossier_composition(
        self, master_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        identity, snapshot, revision, master = self._composition_context(
            master_id, headers, action="view"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if master is None:
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(
            200,
            {
                "item": self._composition_item(identity, snapshot, master, headers),
                "revision": revision.database_revision,
            },
        )

    def _add_dossier_child(
        self, master_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, snapshot, revision, master = self._composition_context(
            master_id, headers, action="edit"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if master is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if str(master.get("dossier_type", "dossier")).strip() != "master":
            return ApiResponse.json(409, {"error": "dossier_not_master"})
        if len(body) > 16_384:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise TypeError
            child_id = str(payload["child_dossier_id"]).strip()
            if not child_id or child_id == master_id or "/" in child_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})

        child = next(
            (
                record
                for record in snapshot.get("dossiers", [])
                if str(record.get("id", "")).strip() == child_id
                and self._same_organization(record, identity.organization_id)
            ),
            None,
        )
        if child is None or not self._composition_allowed(
            identity, "view", child, headers
        ):
            return ApiResponse.json(404, {"error": "child_not_found"})

        existing = next(
            (
                link
                for link in snapshot.get("dossier_links", [])
                if str(link.get("parent_dossier_id", "")).strip() == master_id
                and str(link.get("child_dossier_id", "")).strip() == child_id
                and str(link.get("relationship", "contains")).strip() == "contains"
            ),
            None,
        )
        if existing is not None:
            return ApiResponse.json(
                200,
                {
                    "item": self._composition_item(identity, snapshot, master, headers),
                    "revision": revision.database_revision,
                },
            )

        snapshot.setdefault("dossier_links", []).append(
            {
                "id": str(uuid4()),
                "parent_dossier_id": master_id,
                "child_dossier_id": child_id,
                "relationship": "contains",
            }
        )
        try:
            new_revision = self._science.save_snapshot(
                snapshot, expected_revision=revision
            )
        except ScienceRevisionConflict:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            201,
            {
                "item": self._composition_item(identity, snapshot, master, headers),
                "revision": new_revision.database_revision,
            },
        )

    def _remove_dossier_child(
        self, master_id: str, child_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        identity, snapshot, revision, master = self._composition_context(
            master_id, headers, action="edit"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if master is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if str(master.get("dossier_type", "dossier")).strip() != "master":
            return ApiResponse.json(409, {"error": "dossier_not_master"})

        links = snapshot.get("dossier_links", [])
        remaining = [
            link
            for link in links
            if not (
                str(link.get("parent_dossier_id", "")).strip() == master_id
                and str(link.get("child_dossier_id", "")).strip() == child_id
                and str(link.get("relationship", "contains")).strip() == "contains"
            )
        ]
        if len(remaining) == len(links):
            return ApiResponse.json(404, {"error": "relationship_not_found"})
        snapshot["dossier_links"] = remaining
        try:
            new_revision = self._science.save_snapshot(
                snapshot, expected_revision=revision
            )
        except ScienceRevisionConflict:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            200,
            {
                "item": self._composition_item(identity, snapshot, master, headers),
                "revision": new_revision.database_revision,
            },
        )
