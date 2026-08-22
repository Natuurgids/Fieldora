from pathlib import Path


def test_offline_manuals_are_packaged_and_searchable() -> None:
    root = Path(__file__).parents[1]
    source = (root / "src/natureai_next/ui/qt/manuals_app.py").read_text()
    for name in ("installation.md", "administrator.md", "user.md"):
        path = root / "src/natureai_next/resources/manuals" / name
        assert path.is_file()
        assert len(path.read_text(encoding="utf-8")) > 5_000
        assert name in source
    assert "Search all Fieldora manuals" in source
    assert "setMarkdown" in source


def test_fieldora_exposes_manuals_as_menu_and_gui_entry_point() -> None:
    root = Path(__file__).parents[1]
    application = (root / "src/natureai_next/ui/qt/application.py").read_text()
    project = (root / "pyproject.toml").read_text()
    assert 'QAction("Fieldora Manuals…"' in application
    assert "FieldoraManualsWindow" in application
    assert 'fieldora-manuals = "natureai_next.bootstrap.manuals_app:main"' in project
