from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class WorkspaceContextEvent:
    topic: str
    actor_id: str
    project_id: str = ""
    source: str = ""


class WorkspaceContext:
    """Process-wide desktop context for identity, project and refresh propagation.

    The context deliberately owns no domain data.  It resolves fresh project and
    permission information through the supplied services and only coordinates
    selection/invalidation events between otherwise independent workspaces.
    """

    _instance: "WorkspaceContext | None" = None
    _instance_lock = RLock()

    def __init__(self) -> None:
        self._lock = RLock()
        self._project_id = ""
        self._listeners: list[Callable[[WorkspaceContextEvent], None]] = []

    @classmethod
    def current(cls) -> "WorkspaceContext":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def actor_id(self) -> str:
        return str(os.environ.get("FIELDORA_IDENTITY_ID") or "local-user")

    @property
    def profile_role(self) -> str:
        return str(os.environ.get("FIELDORA_PROFILE_ROLE") or "")

    @property
    def active_project_id(self) -> str:
        with self._lock:
            return self._project_id

    def subscribe(self, listener: Callable[[WorkspaceContextEvent], None]) -> Callable[[], None]:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def publish(self, topic: str, *, project_id: str = "", source: str = "") -> None:
        event = WorkspaceContextEvent(topic, self.actor_id, project_id, source)
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except RuntimeError:
                # A Qt receiver may already have been deleted.
                continue

    def set_active_project(self, project_id: str | None, *, source: str = "") -> None:
        value = str(project_id or "")
        with self._lock:
            changed = value != self._project_id
            self._project_id = value
        if changed:
            self.publish("project.changed", project_id=value, source=source)

    def identity_changed(self, *, source: str = "") -> None:
        self.publish("identity.changed", project_id=self.active_project_id, source=source)

    def permissions_changed(self, project_id: str = "", *, source: str = "") -> None:
        self.publish("permissions.changed", project_id=project_id, source=source)

    def data_changed(self, project_id: str = "", *, source: str = "") -> None:
        self.publish("data.changed", project_id=project_id, source=source)

    def accessible_projects(self, service: Any, permission: str = "view") -> tuple[dict[str, Any], ...]:
        """Return a fresh, deduplicated project list for the active identity.

        Explicit ownership is included for old clean-install fixtures that lack a
        corresponding membership row.  No result is cached.
        """
        actor = self.actor_id
        visible: dict[str, dict[str, Any]] = {
            str(row["project_id"]): dict(row)
            for row in service.accessible_projects(actor, permission=permission)
        }
        try:
            projects = service.projects()
        except (AttributeError, OSError, ValueError):
            projects = ()
        for project in projects:
            project_id = str(getattr(project, "project_id", ""))
            if not project_id or project_id in visible:
                continue
            if str(getattr(project, "owner_id", "")) != actor:
                continue
            visible[project_id] = {
                "project_id": project_id,
                "name": str(getattr(project, "name", project_id)),
                "status": str(getattr(project, "status", "active")),
                "owner_id": actor,
                "due_date": getattr(project, "due_date", None),
                "role": "owner",
            }
        return tuple(visible.values())

    def can(self, service: Any, project_id: str, permission: str) -> bool:
        if not project_id:
            return False
        return bool(service.can(project_id, self.actor_id, permission))
