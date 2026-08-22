from __future__ import annotations

import ast
import re
from pathlib import Path

QT_ROOT = Path(__file__).resolve().parents[1] / "src" / "natureai_next" / "ui" / "qt"


def _classes(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return source, [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def test_every_context_using_workspace_initializes_context() -> None:
    failures: list[str] = []
    for path in QT_ROOT.rglob("*.py"):
        source, classes = _classes(path)
        for cls in classes:
            segment = ast.get_source_segment(source, cls) or ""
            if "self.context" not in segment:
                continue
            if not re.search(r"self\.context\s*=\s*WorkspaceContext\.current\(\)", segment):
                failures.append(f"{path.name}:{cls.name}")
    assert not failures, "Workspace classes use self.context without initializing it: " + ", ".join(failures)


def test_every_subscribed_self_callback_exists_on_its_class() -> None:
    failures: list[str] = []
    for path in QT_ROOT.rglob("*.py"):
        source, classes = _classes(path)
        for cls in classes:
            segment = ast.get_source_segment(source, cls) or ""
            methods = {
                node.name
                for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            for callback in re.findall(r"subscribe\(self\.(\w+)\)", segment):
                if callback not in methods:
                    failures.append(f"{path.name}:{cls.name}.{callback}")
    assert not failures, "Missing subscribed callbacks: " + ", ".join(failures)


def test_research_initializes_context_before_refresh() -> None:
    source = (QT_ROOT / "v5_desktop.py").read_text(encoding="utf-8")
    class_start = source.index("class Research(Page):")
    next_class = source.index("\nclass MeasurementsSampling(Page):", class_start)
    research = source[class_start:next_class]
    assert research.index("self.context=WorkspaceContext.current()") < research.index("self.refresh()")
    assert "def _context_event(self,event):" in research
