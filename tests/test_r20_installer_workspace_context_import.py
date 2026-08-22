from pathlib import Path


def test_application_imports_workspace_context_before_login_use():
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    import_line = "from natureai_next.application.workspace_context import WorkspaceContext"
    use_line = 'WorkspaceContext.current().identity_changed(source="login")'
    assert import_line in source
    assert use_line in source
    assert source.index(import_line) < source.index(use_line)
