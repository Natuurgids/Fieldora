from pathlib import Path


def test_model_manager_imports_qframe_before_subclassing():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/natureai_next/ui/qt/model_manager.py").read_text(encoding="utf-8")
    imports = source.split("class _ModelInstallProgress", 1)[0]
    assert "QFrame" in imports
    assert "class _ModelInstallProgress(QFrame):" in source
