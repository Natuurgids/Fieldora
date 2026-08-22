from pathlib import Path


def test_map_workspace_uses_the_shared_science_project_database() -> None:
    source = (Path(__file__).parents[1] / "src" / "natureai_next" / "bootstrap" / "cli.py").read_text(encoding="utf-8")
    assert 'container.paths.subsystem_databases_dir / "science.sqlite3"' in source
    assert "project_database_path=" in source
    map_factory = source[source.index("def map_workspace_factory"):source.index("def knowledge_center_workspace_factory")]
    assert "opened.connection_factory.database_path" not in map_factory
