"""One-shot deterministic patcher for desktop security composition.

This exists only to bridge a repository API that cannot patch large files. Every
replacement is exact and fail-closed; remove this script after the patch lands.
"""
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


application = Path("src/natureai_next/ui/qt/application.py")
text = application.read_text(encoding="utf-8")
text = replace_once(text, "from natureai_next.bootstrap.startup_timing import StartupTimeline\n", "from natureai_next.bootstrap.paths import ApplicationPaths\nfrom natureai_next.bootstrap.startup_timing import StartupTimeline\n", "ApplicationPaths import")
text = replace_once(text, "        offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,\n    ) -> None:\n", "        offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,\n        application_paths: ApplicationPaths,\n        access_actor_id: str,\n    ) -> None:\n", "MainWindow security parameters")
text = replace_once(text, "        self._offline_map_setup_factory = offline_map_setup_factory\n        self._update_settings_path = session_path.parent / \"update-settings.json\"\n        self._update_staging_directory = session_path.parent / \"updates\" / \"staging\"\n", "        self._offline_map_setup_factory = offline_map_setup_factory\n        self._application_paths = application_paths\n        self._access_actor_id = access_actor_id.strip()\n        self._update_settings_path = application_paths.updates_dir / \"update-settings.json\"\n        self._update_staging_directory = application_paths.updates_dir / \"staging\"\n", "root-bound update paths")
text = replace_once(text, "        self._update_service = OfflineUpdateService()\n        self._update_history_store = UpdateHistoryStore()\n        self._update_history_path = session_path.parent / \"updates\" / \"update-history.jsonl\"\n", "        self._update_service = OfflineUpdateService(\n            trust_anchor_path=application_paths.update_trust_anchor_file\n        )\n        self._update_history_store = UpdateHistoryStore()\n        self._update_history_path = application_paths.updates_dir / \"update-history.jsonl\"\n", "trusted update service")
text = text.replace("resolve_application_paths().subsystem_databases_dir", "application_paths.subsystem_databases_dir")
text = text.replace("resolve_application_paths().models_dir", "application_paths.models_dir")
text = text.replace("resolve_application_paths().plugins_dir", "application_paths.plugins_dir")
text = replace_once(text, "                SqliteAccessControlRepository(\n                    application_paths.subsystem_databases_dir\n                    / \"access-control.sqlite3\"\n                )\n            ),\n", "                SqliteAccessControlRepository(\n                    application_paths.subsystem_databases_dir\n                    / \"access-control.sqlite3\"\n                ),\n                actor_id=self._access_actor_id,\n            ),\n", "authenticated PBAC actor")
text = replace_once(text, "            augment_request(\n                staged.request_path, parent_pid=os.getpid(), library_path=self._session_path.parent\n            )\n", "            augment_request(\n                staged.request_path,\n                parent_pid=os.getpid(),\n                library_path=self._session_path.parent,\n                config_root=self._application_paths.local_root,\n                trust_anchor_path=self._application_paths.update_trust_anchor_file,\n            )\n", "root-bound pending request")
text = replace_once(text, "                    parent_pid=os.getpid(),\n                    library_path=self._session_path.parent,\n                )\n", "                    parent_pid=os.getpid(),\n                    library_path=self._session_path.parent,\n                    config_root=self._application_paths.local_root,\n                    trust_anchor_path=self._application_paths.update_trust_anchor_file,\n                )\n", "root-bound updater launch")
text = replace_once(text, "    offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,\n    on_about_to_quit: Callable[[], None] = lambda: None,\n", "    offline_map_setup_factory: Callable[[QWidget], QDialog] | None = None,\n    application_paths: ApplicationPaths,\n    on_about_to_quit: Callable[[], None] = lambda: None,\n", "run_desktop application paths")
text = replace_once(text, "    os.environ[\"FIELDORA_IDENTITY_ID\"] = str(login.profile[\"username\"])\n    WorkspaceContext.current().identity_changed(source=\"login\")\n", "    access_actor_id = str(login.profile[\"username\"]).strip()\n    if not access_actor_id:\n        raise RuntimeError(\"authenticated desktop identity is required\")\n    os.environ[\"FIELDORA_IDENTITY_ID\"] = access_actor_id\n    WorkspaceContext.current().identity_changed(source=\"login\")\n", "authenticated actor capture")
text = replace_once(text, "            offline_map_setup_factory=offline_map_setup_factory,\n        )\n", "            offline_map_setup_factory=offline_map_setup_factory,\n            application_paths=application_paths,\n            access_actor_id=access_actor_id,\n        )\n", "MainWindow composition arguments")
application.write_text(text, encoding="utf-8")

cli = Path("src/natureai_next/bootstrap/cli.py")
text = cli.read_text(encoding="utf-8")
text = replace_once(text, "                    update_settings_path=session_path.parent / \"update-settings.json\",\n", "                    update_settings_path=container.paths.updates_dir / \"update-settings.json\",\n", "health update root")
text = replace_once(text, "                offline_map_setup_factory=offline_map_setup_factory,\n                health_service=LibraryHealthService(\n", "                offline_map_setup_factory=offline_map_setup_factory,\n                application_paths=container.paths,\n                health_service=LibraryHealthService(\n", "bootstrap application paths")
cli.write_text(text, encoding="utf-8")

test = Path("tests/test_desktop_security_composition.py")
test.write_text('''from pathlib import Path\n\n\ndef test_desktop_composition_binds_security_context_explicitly() -> None:\n    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")\n    assert "application_paths: ApplicationPaths" in source\n    assert "trust_anchor_path=application_paths.update_trust_anchor_file" in source\n    assert "actor_id=self._access_actor_id" in source\n    assert "config_root=self._application_paths.local_root" in source\n    assert "trust_anchor_path=self._application_paths.update_trust_anchor_file" in source\n    assert "resolve_application_paths().subsystem_databases_dir" not in source\n    assert "resolve_application_paths().models_dir" not in source\n    assert "resolve_application_paths().plugins_dir" not in source\n    assert 'session_path.parent / "update-settings.json"' not in source\n    assert 'session_path.parent / "updates" / "staging"' not in source\n    assert 'session_path.parent / "updates" / "update-history.jsonl"' not in source\n\n\ndef test_bootstrap_passes_resolved_paths_to_desktop() -> None:\n    source = Path("src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")\n    assert "application_paths=container.paths" in source\n    assert 'update_settings_path=container.paths.updates_dir / "update-settings.json"' in source\n''', encoding="utf-8")
