from __future__ import annotations

import ast
from pathlib import Path


def test_workspace_context_references_are_imported() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "natureai_next"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "WorkspaceContext" not in text or path.name == "workspace_context.py":
            continue
        tree = ast.parse(text, filename=str(path))
        imported = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "natureai_next.application.workspace_context"
            and any(alias.name == "WorkspaceContext" for alias in node.names)
            for node in tree.body
        )
        if not imported:
            offenders.append(str(path.relative_to(src.parent.parent)))
    assert offenders == []
