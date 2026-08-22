from pathlib import Path


ROOT = Path(__file__).parents[1]
V5 = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
APP = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
REPORTING = (ROOT / "src/natureai_next/ui/qt/reporting.py").read_text(encoding="utf-8")


def test_v5_controls_preserve_domain_context() -> None:
    for route in (
        "__asset_collection__:", "__asset_export__:", "__asset_open__:",
        "__observation_evidence__:", "__observation_map__:", "__observation_record__:",
        "__project_open__:", "__project_map__:",
    ):
        assert route in V5 or route.removesuffix(":") in V5
        assert route in APP


def test_v5_search_and_status_tabs_filter_live_tables() -> None:
    assert "self.search.textChanged.connect(self._search_changed)" in V5
    assert "self.table.filter_text(self.search_text())" in V5
    assert "v5/observation_filter" in V5
    assert "v5/knowledge_tab" in V5


def test_help_search_opens_filtered_offline_help() -> None:
    assert "__help_search__:" in V5
    assert "dialog._search.setText(query)" in APP


def test_observation_org_supports_oauth_and_media() -> None:
    assert "authorization_url" in REPORTING
    assert "exchange_code" in REPORTING
    assert "upload_media(remote_id, source)" in REPORTING
    assert "not stored" in REPORTING


def test_v5_export_selection_is_in_shared_selection_provider() -> None:
    assert "self._v5_selected_asset_ids" in APP
    assert "+ self._v5_selected_asset_ids" in APP
