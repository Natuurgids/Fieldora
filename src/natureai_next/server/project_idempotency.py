"""Replay-safe Project creation for managed browser mutations."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.postgres_project_management import (
    PostgresProjectManagementService,
    _id,
    _now_us,
    _validate_project_dates,
)


class ProjectMutationConflict(ValueError):
    """A mutation identity was reused with a different create payload."""


class IdempotentProjectManagementFacade:
    """Add caller-keyed Project creation without changing the managed service API."""

    def __init__(self, delegate: PostgresProjectManagementService) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def create_project_idempotent(
        self,
        project_id: str,
        name: str,
        *,
        organization_id: str,
        owner_id: str,
        actor_id: str,
        start_date: str = "",
        due_date: str = "",
        description: str = "",
        budget: float = 0,
        currency: str = "EUR",
        template_id: str | None = None,
    ) -> tuple[str, bool]:
        organization = organization_id.strip()
        normalized_name = name.strip()
        normalized_owner = owner_id.strip()
        normalized_description = description.strip()
        normalized_currency = currency.strip() or "EUR"
        if not organization:
            raise ValueError("organization is required")
        if not normalized_name:
            raise ValueError("project name is required")
        _validate_project_dates(start_date, due_date)
        if template_id:
            raise ValueError(
                "project templates are not yet available in the managed PostgreSQL adapter"
            )

        expected = (
            organization,
            normalized_name,
            normalized_description,
            "active",
            normalized_owner,
            start_date,
            due_date,
            float(budget),
            normalized_currency,
            template_id,
        )
        statuses = (
            ("To Do", "todo", "#6b7280"),
            ("In Progress", "active", "#2563eb"),
            ("QA", "review", "#7c3aed"),
            ("Blocked", "blocked", "#dc2626"),
            ("Done", "done", "#16a34a"),
        )
        member_id = normalized_owner or actor_id
        now = _now_us()
        with self._delegate._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"fieldora:web049:{project_id}",),
                )
                cursor.execute(
                    """
                    SELECT organization_id,name,description,status,owner_id,start_date,
                           due_date,budget,currency,template_id
                    FROM pm_projects WHERE project_id=%s
                    """,
                    (project_id,),
                )
                row = cursor.fetchone()
                if row is not None:
                    actual = (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        str(row[5]),
                        str(row[6]),
                        float(row[7]),
                        str(row[8]),
                        None if row[9] is None else str(row[9]),
                    )
                    if actual != expected:
                        raise ProjectMutationConflict(
                            "project mutation identity already belongs to another payload"
                        )
                    return project_id, True

                cursor.execute(
                    """
                    INSERT INTO pm_projects(
                        project_id,organization_id,name,description,status,owner_id,
                        start_date,due_date,budget,currency,template_id,client_name,
                        created_at_us,updated_at_us
                    ) VALUES(%s,%s,%s,%s,'active',%s,%s,%s,%s,%s,%s,'',%s,%s)
                    """,
                    (
                        project_id,
                        organization,
                        normalized_name,
                        normalized_description,
                        normalized_owner,
                        start_date,
                        due_date,
                        float(budget),
                        normalized_currency,
                        template_id,
                        now,
                        now,
                    ),
                )
                for order, (status_name, category, color) in enumerate(statuses):
                    cursor.execute(
                        """
                        INSERT INTO pm_statuses(
                            status_id,project_id,name,category,color,display_order,wip_limit
                        ) VALUES(%s,%s,%s,%s,%s,%s,NULL)
                        """,
                        (_id(), project_id, status_name, category, color, order),
                    )
                cursor.execute(
                    "INSERT INTO pm_project_members(project_id,user_id,role) "
                    "VALUES(%s,%s,'admin')",
                    (project_id, member_id),
                )
                self._delegate._event(
                    cursor,
                    project_id,
                    actor_id,
                    "project.created",
                    {"name": normalized_name},
                )
        return project_id, False


def wrap_project_management(service: Any) -> Any:
    """Wrap only the managed PostgreSQL Project service."""
    if isinstance(service, IdempotentProjectManagementFacade):
        return service
    if isinstance(service, PostgresProjectManagementService):
        return IdempotentProjectManagementFacade(service)
    return service


class ProjectIdempotencyApiMixin:
    """Require a stable mutation identity for managed browser Project creates."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        service = getattr(self, "_project_management", None)
        if (
            method != "POST"
            or route.path != "/api/v1/projects"
            or not hasattr(service, "create_project_idempotent")
        ):
            return super().dispatch(method, target, headers, body)
        return self._create_project_idempotent(headers, body)

    def _create_project_idempotent(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        try:
            record = json.loads(body)
            if not isinstance(record, dict):
                raise ValueError
            project_id = str(record["id"]).strip()
            UUID(project_id)
            name = str(record["name"]).strip()
            if not name:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})

        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "create",
                "project",
                project_id,
                identity.organization_id,
                "",
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})

        try:
            created_id, replayed = self._project_management.create_project_idempotent(
                project_id,
                name,
                organization_id=identity.organization_id,
                owner_id=identity.identity_id,
                actor_id=identity.identity_id,
                start_date=str(record.get("start_date") or ""),
                due_date=str(record.get("due_date") or ""),
                description=str(record.get("description") or ""),
                budget=float(record.get("budget") or 0),
                currency=str(record.get("currency") or "EUR"),
                template_id=(
                    str(record["template_id"]).strip()
                    if record.get("template_id")
                    else None
                ),
            )
        except ProjectMutationConflict:
            return ApiResponse.json(409, {"error": "idempotency_conflict"})
        except (TypeError, ValueError) as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )

        if not replayed:
            self._grant_project_owner(
                identity.identity_id,
                identity.organization_id,
                created_id,
                name,
            )
        item = self._project_for_organization(identity.organization_id, created_id)
        assert item is not None
        return ApiResponse.json(
            200 if replayed else 201,
            {
                "item": self._project_item(item),
                "revision": item.revision,
                "replayed": replayed,
            },
        )
