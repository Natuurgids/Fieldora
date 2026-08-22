from __future__ import annotations

from dataclasses import dataclass

from natureai_next.application.workspace_context import WorkspaceContext


@dataclass
class Project:
    project_id: str
    name: str
    status: str
    owner_id: str
    due_date: str | None = None


class Service:
    def accessible_projects(self, user_id: str, permission: str = "view"):
        assert permission == "view"
        return ({"project_id": "member", "name": "Member", "status": "active", "owner_id": "other"},)

    def projects(self):
        return (
            Project("member", "Member", "active", "other"),
            Project("owned", "Owned", "active", "alice"),
            Project("hidden", "Hidden", "active", "bob"),
        )

    def can(self, project_id: str, user_id: str, permission: str):
        return (project_id, user_id, permission) == ("member", "alice", "edit")


def fresh_context(monkeypatch):
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "alice")
    return WorkspaceContext()


def test_accessible_projects_are_fresh_deduplicated_and_include_explicit_owner(monkeypatch):
    context = fresh_context(monkeypatch)
    rows = context.accessible_projects(Service())
    assert [row["project_id"] for row in rows] == ["member", "owned"]
    assert rows[1]["role"] == "owner"


def test_context_publishes_project_identity_permission_and_data_events(monkeypatch):
    context = fresh_context(monkeypatch)
    events = []
    unsubscribe = context.subscribe(events.append)
    context.set_active_project("p1", source="test")
    context.identity_changed(source="test")
    context.permissions_changed("p1", source="test")
    context.data_changed("p1", source="test")
    unsubscribe()
    context.data_changed("p1", source="ignored")
    assert [(e.topic, e.project_id) for e in events] == [
        ("project.changed", "p1"),
        ("identity.changed", "p1"),
        ("permissions.changed", "p1"),
        ("data.changed", "p1"),
    ]


def test_context_permission_check_uses_current_identity(monkeypatch):
    context = fresh_context(monkeypatch)
    assert context.can(Service(), "member", "edit") is True
    assert context.can(Service(), "member", "manage") is False
