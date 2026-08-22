from __future__ import annotations

import ast
from pathlib import Path

from natureai_next.ui.qt.navigation_contracts import (
    V5_WORKSPACE_SPECS,
    is_supported_route,
    normalize_route,
    validate_page_mapping,
    workspace_names,
)


class _Signal:
    def connect(self, _slot):
        return None


class _Page:
    route_requested = _Signal()

    def refresh(self):
        return None


def test_v5_registry_has_unique_names_and_factories():
    assert len(workspace_names()) == len(set(workspace_names()))
    assert len({spec.factory_name for spec in V5_WORKSPACE_SPECS}) == len(V5_WORKSPACE_SPECS)


def test_page_mapping_validation_rejects_missing_or_duplicate_pages():
    pages = {name: _Page() for name in workspace_names()}
    validate_page_mapping(pages)
    broken = dict(pages)
    broken.pop("Home")
    try:
        validate_page_mapping(broken)
    except RuntimeError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing page was accepted")

    reused = {name: _Page() for name in workspace_names()}
    reused["Help & Guides"] = reused["Home"]
    try:
        validate_page_mapping(reused)
    except RuntimeError as exc:
        assert "reuses page instances" in str(exc)
    else:
        raise AssertionError("duplicate page instance was accepted")


def test_aliases_are_normalized_centrally():
    assert normalize_route("AI Review") == "Knowledge Base"
    assert normalize_route("Taxonomy") == "Knowledge Base"


def test_literal_v5_routes_resolve_to_workspace_or_context_handler():
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    routes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("__") or value in {
                "Photos", "Sounds", "Videos", "Documents", "Map", "Collections",
                "Notebook", "Science Projects", "Measurements & Protocols",
                "Science Dossiers", "Science Whiteboard", "Science Calendar",
                "Maritime Operations", "Export", "Knowledge Base", "Models",
                "Integrations", "Taxonomy Resources", "Diagnostics", "Updates",
                "Preferences", "Library Types", "Access & Contracts",
                "Resource Components", "Offline Maps", "Home", "Help & Guides",
                "Administration Governance", "Research Reference Data",
                "AI Chat & MCP", "AI Platform Administration", "Local Profiles",
            }:
                routes.add(value)
    app_source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    module = ast.parse(app_source)
    workspaces: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "WORKSPACES" for t in node.targets):
            if isinstance(node.value, ast.Tuple):
                workspaces.update(e.value for e in node.value.elts if isinstance(e, ast.Constant))
    unsupported = sorted(route for route in routes if not is_supported_route(route, workspaces))
    assert unsupported == []


def test_build_pages_uses_registry_validation():
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "validate_page_mapping(pages)" in source
