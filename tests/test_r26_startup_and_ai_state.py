from __future__ import annotations

import ast
from pathlib import Path


def _source(relative: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / relative).read_text(encoding="utf-8")


def test_run_desktop_does_not_shadow_module_os_import() -> None:
    tree = ast.parse(_source("src/natureai_next/ui/qt/application.py"))
    run_desktop = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_desktop"
    )
    local_os_imports = [
        node
        for node in ast.walk(run_desktop)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (isinstance(node, ast.Import) and any(alias.name == "os" for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "os")
        )
    ]
    assert local_os_imports == []


def test_provider_change_clears_provider_specific_tool_state() -> None:
    source = _source("src/natureai_next/ui/qt/v5_desktop.py")
    start = source.index(" def _provider_changed")
    end = source.index(" def _load_conversations", start)
    handler = source[start:end]
    assert "self.model.clear()" in handler
    assert "self.tools_list.clear()" in handler
    assert "self.service.models(pid,enabled_only=True)" in handler
