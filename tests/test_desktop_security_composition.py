from pathlib import Path


def test_desktop_composition_binds_security_context_explicitly() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "application_paths: ApplicationPaths" in source
    assert "trust_anchor_path=application_paths.update_trust_anchor_file" in source
    assert "actor_id=self._access_actor_id" in source
    assert "config_root=self._application_paths.local_root" in source
    assert "trust_anchor_path=self._application_paths.update_trust_anchor_file" in source
    assert "resolve_application_paths().subsystem_databases_dir" not in source
    assert "resolve_application_paths().models_dir" not in source
    assert "resolve_application_paths().plugins_dir" not in source
    assert 'session_path.parent / "update-settings.json"' not in source
    assert 'session_path.parent / "updates" / "staging"' not in source
    assert 'session_path.parent / "updates" / "update-history.jsonl"' not in source


def test_bootstrap_passes_resolved_paths_to_desktop() -> None:
    source = Path("src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")
    assert "application_paths=container.paths" in source
    assert 'update_settings_path=container.paths.updates_dir / "update-settings.json"' in source
